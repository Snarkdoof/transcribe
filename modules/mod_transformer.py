import re
import os
try:
    import ftfy
    CANRUN = True
except Exception:
    CANRUN = False
    print("Missing ftfy")


ccmodule = {
    "description": "Transform data using a given model and tokenizer",
    "depends": [],
    "provides": [],
    "inputs": {
        "tokenizer": "Tokenizer ID",
        "model": "Model ID",
        "max_len": "Max output length (in tokens), default 512",
        "src": "Input file",
        "groupOn": "Group by index in CSV file (must be CSV)"
    },
    "outputs": {
        "dst": "Output file"
    },
    "defaults": {
        "priority": 50,  # Normal
        "runOn": "success"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}


class Transformer:
    instance = None

    @staticmethod
    def get():
        if not Transformer.instance:
            Transformer.instance = Transformer()
        return Transformer.instance

    def __init__(self):

        self.tokenizer = None
        self.model = None
        self.tokenizerID = ""
        self.modelID = ""
        self.log = None

    def _calc_len(self, text):
        # text = text[start:end]

        # Clean stuff
        text = text.strip()
        text = " ".join(text.split())
        text = ftfy.fix_text(text)

        # Replace
        trans_chars = " 1234567890'\",.:;-_*?/\n"
        trans_table = text.maketrans("", "", trans_chars)
        text = text.translate(trans_table)

        return len(text)

    def cleanup_output(self, o):

        new_o = []
        for item in o:
            m = re.search("[\.\,]([\,\.]{2,})", item)
            # if not m:
            #    m = re.search("(eee)", item, re.I)
            # if not m:
            #     m = re.search("(qqq)", item, re.I)
            if m:
                new_o.append(item.replace(m.groups()[0], ""))
                # new_o.append(item[:m.span(0)[0] + 1])
            else:
                new_o.append(item)
        return new_o

    def process_task(self, cc, task):

        self.log = cc.log

        args = task["args"]

        max_len = args.get("max_length", 512)

        if "model" not in args or "tokenizer" not in args:
            raise Exception("Require both model and tokenizer")

        if "dst" not in args:
            d, f = os.path.split(args["src"])
            args["dst"] = os.path.join(d, "transformed-%s" % f)

        if os.path.exists(args["dst"]) and os.path.getsize(args["dst"]) > 0:
            cc.log.warning("Cache failed to catch this one")
            return 100, {"result": "ok", "dst": args["dst"]}

        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        import torch
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

        if not self.tokenizer or self.tokenizerID != args["tokenizer"]:
            cc.log.info("Loading tokenizer %s" % args["tokenizer"])
            self.tokenizer = AutoTokenizer.from_pretrained(args["tokenizer"])
            self.tokenizerID = args["tokenizer"]

        if not self.model or self.modelID != args["model"]:
            cc.log.info("Loading model %s" % args["model"])
            self.model = AutoModelForSeq2SeqLM.from_pretrained(args["model"]).to(device)
            self.modelID = args["model"]
            self.model.config.max_length = max_len
            self.model.config.task_specific_params["translation"]["max_length"] = max_len
            self.model.config.task_specific_params["text-generation"]["max_length"] = max_len

        # We're ready to lock and load!

        # Recognized: CSV, pure text
        if not os.path.exists(args.get("src", "")):
            raise Exception("Missing source file '%s'" % args.get("src", ""))

        fmt = "text"
        if args["src"].endswith("csv"):
            fmt = "csv"

        if args.get("groupOn", None) is not None:
            if fmt == "text":
                raise Exception("Can't group text")
            output = self.process_file_group(args["src"], device, fmt, args["groupOn"])
        else:
            output = self.process_file(args["src"], device, fmt)

        with open(args["dst"], "w") as f:
            f.write(output)

        return 100, {"result": "ok", "dst": args["dst"]}

    def process_text(self, text, device):

        if text.find("\n") > -1 or text.find("\r") > -1:
            raise Exception("Newline where no newline is expected")
        print("---- processing ----")
        print(text.replace(" ", ""))
        translated = self.model.generate(**self.tokenizer(text.replace(" ", ""), return_tensors="pt", padding=True).to(device))
        o = [self.tokenizer.decode(t, skip_special_tokens=True) for t in translated]
        o = self.cleanup_output(o)

        if len(o[0]) - len(text) > max(5, (len(text) * 0.2)):
            # We added more than *5* pieces of punctuation, seems suspect
            print(" *** SUSPECT: '%s' -> '%s'" % (text, o[0]))
            o = [text]

        print("   ***   ")
        print(o)
        print()

        return o

    def process_file(self, filename, device, fmt):

        output = ""
        with open(filename) as f:
            for line in f.readlines():
                if fmt == "csv":
                    text = line[line.rfind(",") + 1:].strip()
                else:
                    text = line.strip()

                if len(text) < 2:
                    continue  # Skip empty lines

                o = self.process_text(text, device)

                # print("'%s'" % text)
                # print(o)

                if fmt == "csv":
                    output += line[:line.rfind(",")] + "," + " ".join(o) + "\n"
                    # print(line[:line.rfind(",")] + "," + o[0])
                else:
                    output += " ".join(o)

        return output

    def process_file_group(self, filename, device, fmt, group_by, text_at=-1, reformat=True):
        """
        group_by is the "key" or index of what to group by, text_at is the
        key/index that has the text item.

        Process a file but group by the given item - for example "who" means
        that all following items from the same "who" is grouped, then
        transformed, then returned to the splits that they had. For example:
        'this is a test of'
        'something rather nice' Will be processed as 'this is a test of
         something rather nice', converted possibly to 'This is a test of
         something rather nice.' and returned at the end as 'This is a test
         of', 'something rather nice.'

        reformat if set to true will allow the entries to be reformatted based
        on sentences, not on their original split
        """
        output = ""

        current_block = []

        with open(filename) as f:
            lines = f.readlines()

        for linenr, line in enumerate(lines):
            if linenr == 0:
                continue

            data = line.split(",")

            # Group this
            if linenr < len(lines):
                if len(current_block) == 0:
                    current_block.append(data)
                    continue

                # We also check the time - if there's a gap, skip the block
                START = 1
                END = 2
                MAX_GAP_S = 0.7
                MAX_LEN = 1000  # Only add more if

                # Is this block part of the gruop, or is it new?
                # If new, the "old" block is done, and we'll process it
                if len(" ".join([x[text_at] for x in current_block])) < MAX_LEN:
                    if current_block[-1][group_by] == data[group_by]:
                        # If the gap between the texts is less than MAX_GAP_S, gruop.
                        if float(data[START]) - float(current_block[-1][END]) < MAX_GAP_S:
                            current_block.append(data)
                            continue

            # It's different, process the last block
            text = " ".join([x[text_at].replace("\n", " ").strip() for x in current_block]).strip()
            o = self.process_text(text, device)

            # We must now "go back" to the bits we had and add them as lines
            start_idx = end_idx = 0

            # ENSURE that the first letter is a big one - this is a new person
            # speaking, we assume it's going to be a large letter, right?
            trans_text = o[0][0].upper() + o[0][1:]

            # We can merge "back" into the blocks we had or we can re-create the entries
            # based on the sentences we've created

            if reformat:
                WHO = 0
                START = 1
                END = 2
                FILENAME = 4

                # Timestamp each original char according to the trimmed version
                timestamps = []
                for item in current_block:
                    start = float(item[START])
                    end = float(item[END])
                    tlen = self._calc_len(item[text_at])
                    if tlen == 0:  # Likely empty or only punctuation
                        continue

                    tpc = (end - start) / tlen
                    for i in range(tlen):
                        timestamps.append(start + ((i + 1) * tpc))

                if len(timestamps) == 0:
                    self.log.warning("No timestamps for text '%s'" % trans_text)
                    continue

                # We can now figure out the start and end times based on the character number
                sentences = re.split("(?<=\!)|(?<=\?)|(?<=\.)", trans_text.replace("\n", " "))
                str_idx = 0  # according to calc_len
                for sentence in sentences:
                    if not sentence.strip():
                        continue  # Ignore blanks

                    start = timestamps[min(len(timestamps) - 1, str_idx)]
                    print(" start", str_idx)
                    str_idx = min(len(timestamps) - 1, str_idx + self._calc_len(sentence))
                    print("  end", str_idx, len(timestamps))
                    end = timestamps[str_idx]

                    print("   " + ",".join([current_block[0][WHO], str(start), str(end),
                                        str(end - start),
                                        current_block[0][FILENAME], sentence]) + "\n")
                    # Now we can write it to file too!
                    output += ",".join([current_block[0][WHO], str(start), str(end),
                                        str(end - start),
                                        current_block[0][FILENAME], sentence]).strip() + "\n"

            else:
                for item in current_block:

                    # We calculate the length using a "reverse" function for the AI
                    orig_text = item[text_at]
                    orig_len = self._calc_len(orig_text)

                    # Now we look (a bit inefficiently ok) for the same length transformed string
                    # The string should start at start_idx and we'll adjust end_idx until it's correct
                    end_idx = start_idx + orig_len  # At least the same length

                    while end_idx < len(trans_text):
                        new_len = self._calc_len(trans_text[start_idx:end_idx])
                        if new_len > orig_len:  # We stop when we pass the length as punctuation is often at the end too
                            end_idx -= 1
                            break
                        end_idx += 1

                    # Replace the text
                    # new_text = " ".join(transformed[start_idx:end_idx])
                    new_text = trans_text[start_idx:end_idx]
                    # print(item[1], orig_text, "\n->\n" + item[1], new_text.strip())
                    start_idx = end_idx

                    # Now we can write it to file too!
                    output += ",".join(item[:-1]) + "," + new_text.strip() + "\n"

            # We processed up til the current data element, queue it for processing
            current_block = [data]

        return output


def process_task(cc, task):

    transformer = Transformer.get()
    return transformer.process_task(cc, task)
