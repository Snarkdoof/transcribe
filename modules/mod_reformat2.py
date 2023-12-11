import json
import re
import math
import textwrap
import os

ccmodule = {
    "description": "Reformat subs based on whisper_timestamp with timestamped words",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Source file to convert",
        "dst": "Destination file",
        "basename": "Base name for result files",
        "format": "vtt, json",
        "max_chars_per_line": "Maximum chars pr line, default 37",
        "max_time_pr_sub": "Maximum time span for a subtitle default 6.0 seconds"
    },
    "outputs": {
        "dst": "Output fancysub file"
    },
    "defaults": {
        "priority": 50,  # Normal        "runOn": "success"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}


def fix_first_segment(segments):
    # The first segment seems to be super badly timestamped, with the first
    # word being listed as lasting for seconds. If this is the case, move the
    # start of the first segment and the first word to something a bit more
    # sensible.

    first_word = segments[0]["words"][0]

    speed = [len(w["text"]) / (w["end"] - w["start"]) for w in segments[0]["words"][1:]]
    if len(speed) == 0:
        print(" **** No speed")
        return segments

    avg_speed = sum(speed) / len(speed)
    est_start = first_word["end"] - (len(first_word["text"]) / avg_speed)
    if abs(est_start - first_word["start"]) > 0.5:
        segments[0]["words"][0]["start"] = max(0, est_start)
        segments[0]["start"] = max(0, est_start)

    return segments

def fix_segment_start(segment):
    # Some segments, in particular the first one after a while, has a start
    # point that is very wrong. If the first word lasts for much longer than
    # the average duration of the rest of the words, change the timestamp to
    # be more sensible
    if len(segment["words"]) == 0:
        return segment

    first_word = segment["words"][0]

    for w in segment["words"]:
        if w["end"] == w["start"]:
            print("word with no time", segment)

    speed = [len(w["text"]) / max(1, (w["end"] - w["start"])) for w in segment["words"][1:]]
    if len(speed) == 0:
        return segment

    avg_speed = sum(speed) / len(speed)
    est_start = first_word["end"] - (len(first_word["text"]) / avg_speed)
    if segment["words"][1]["start"] - first_word["end"] > 1.0: # Huge gap to next word
        segment["start"] = max(0, segment["words"][1]["start"] - (len(first_word["text"]) / avg_speed))
        segment["words"][0]["start"] = max(0, segment["start"])
        segment["words"][0]["end"] = segment["words"][1]["start"]
    elif abs(est_start - first_word["start"]) > 0.5:
        segment["words"][0]["start"] = max(0, est_start)
        segment["start"] = max(0, est_start)

    return segment


def merge_segments(segments):
    # We go through the segments and merge those that are next to each other and
    # doesn end with some sort of full stop

    fullstops = "[\.?!]"

    new_segments = []

    # First segment is tricky, often due to jingles
    #segments = fix_first_segment(segments)

    merge_segment = None
    for segment in segments:

        if not "text" in segment or not segment["text"]:
            print("Not a text segment")
            continue

        if "words" not in segment:
            print("Weird segment!", segment)
        segment = fix_segment_start(segment)

        # If the text segment is a list, concat them
        if isinstance(segment["text"], list):
            segment["text"] = "\n".join(segment["text"])
        if segment["text"] and re.match(fullstops, segment["text"].strip()[-1]):

            # Ends on a full stop, keep it
            if merge_segment:
                # Need to merge two segments
                merge_segment["text"] += " " + segment["text"]
                merge_segment["end"] = segment["end"]
                merge_segment["words"].extend(segment["words"])
                new_segments.append(merge_segment)
            else:
                new_segments.append(segment)
            merge_segment = None
            continue

        # Not the end, we'll continue on this one
        if merge_segment:
            merge_segment["text"] += segment["text"]
            merge_segment["end"] = segment["end"]
            merge_segment["words"].extend(segment["words"])
        else:
            merge_segment = segment

        # Ensure that there is a space after any comma
        merge_segment["text"] = re.sub(r',(\w)', r', \1', merge_segment["text"])
        merge_segment["text"] = re.sub(r'  ', r' ', merge_segment["text"])

    # print(len(segments), "converted to", len(new_segments))
    return new_segments

def similar_word(word1, word2, threshold=80):
    from fuzzywuzzy import fuzz
    similarity = fuzz.ratio(word1, word2)
    return similarity >= threshold

def resynchronize(modified_string, original_word_list, similarity_threshold=80):
    import difflib
    modified_words = modified_string.replace("\n", " ").split()
    original_words = [word_obj["text"] for word_obj in original_word_list]

    matcher = difflib.SequenceMatcher(None, original_words, modified_words, autojunk=False)
    synchronized_word_list = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            synchronized_word_list.extend(original_word_list[i1:i2])
        elif op == "insert":
            for _ in range(j1, j2):
                if len(synchronized_word_list) > 0:
                    synchronized_word_list.append({"text": "", "start": synchronized_word_list[-1]["end"], "end": synchronized_word_list[-1]["end"]})
                else:
                    synchronized_word_list.append({"text": "", "start": 0, "end": 0})

        elif op == "delete":
            # We want an empty one here
            synchronized_word_list.append({"text": "", "start": 0, "end": 0})
            pass
        elif op == "replace":
            for index in range(j1, j2):
                # If the modified words is just concatenated, we ignore it -
                # this is a bit of a hack that shouldn't be necessary, but we
                # get some of these in particular when whisper is repeating
                # itself/hallucinating
                if modified_words[j1:j2][0] == "".join(original_words[i1:i2]):
                    for original_word_obj in original_word_list[i1:i2]:
                        synchronized_word_list.append(original_word_obj)
                    continue
                modified_word = modified_words[index]
                for original_word_obj in original_word_list[i1:i2]:
                    if similar_word(modified_word, original_word_obj["text"], similarity_threshold):
                        synchronized_word_list.append(original_word_obj)
                        break
                else:
                    if len(synchronized_word_list) > 0:
                        synchronized_word_list.append({"text": "", "start": synchronized_word_list[-1]["end"], "end": synchronized_word_list[-1]["end"]})
                    else:
                        synchronized_word_list.append({"text": "", "start": 0, "end": 0})

    # We now have a list of words that is "sensible" for the new words, but
    # the words are not the same. Use the new words?
    for idx, w in enumerate(synchronized_word_list):
        if idx < len(modified_words):
            w["updated"] = modified_words[idx]
        else:
            w["updated"] = ""
    return synchronized_word_list


def get_cut_point(words, max_time, max_chars, pause_threshold=0.6):
    if len(words) == 0:
        return 0

    cut = cut_stop = cut_pause = cut_space = cut_punctuation = textlen = 0
    start_ts = last_end_time = words[0]["start"]
    for i, word in enumerate(words):
        textlen += len(word["text"])
        if textlen > max_chars:
            break
        if word["start"] - start_ts > max_time:
            break

        if word["text"][-1] in [".", "!", "?"]:
            cut_stop = i  # Fullstop

        if word["text"][-1] in [",", ":"]:
            cut_punctuation = i  # punctuation

        if word['start'] - last_end_time > pause_threshold:
            cut_pause = i - 1  # Too long time

        cut_space = i
        last_end_time = word["end"]

    cut = max(cut_pause, cut_stop, cut_space)
    if cut == 0:
        return 0

    # Is there a space close to the end?
    if cut_pause / cut > 0.6:
        # Go for the pause
        cut = cut_pause

    if cut_punctuation / cut > 0.7:
        # Go for the punctuation
        cut = cut_punctuation

    if cut_stop / cut > 0.6:
        # Go for the fullstop
        cut = cut_stop

    # The pause is actually very important. Always use it
    if cut_pause and cut_pause < cut:
        cut = cut_pause

    # Is there a single word after the cut with a space or a full stop?
    # TODO: Rather use length of words
    if len(words) > cut + 1 and words[cut + 1]["text"][-1] in [".", ",", "!", "?"]:
        cut += 1
    # Two words? :-/
    if len(words) > cut + 2 and words[cut + 2]["text"][-1] in [".", ",", "!", "?"]:
        cut += 2

    # If cut is 0 (we found NOTHING, we must return the end)
    if not cut:
        return len(words)

    return cut


def split_segments(segments, max_chars, max_cps=20.0, max_time=7.0):
    """
    Split segments, ensure that they are within the maximum amount of chars.
    If there is punctuation in the final 30%, split on that.
    max_cps is maximum chars pr second - will adjust the minimum length of a sub
    """
    SIMILARITY = 50  # How similar to detect as same word?

    new_segments = []
    for segment in segments:

        # duration - if it's too long, we split
        if (max_time is None or segment["end"] - segment["start"] < max_time) and \
            len(segment["text"]) < max_chars:
                new_segments.append(segment)
                continue

        fulltext = segment["text"].strip()
        text = segment["text"].strip()
        resynced = resynchronize(fulltext, segment["words"], SIMILARITY)

        words = [w["updated"] for w in resynced]
        words = fulltext.replace("\n", " ").split()
        # words = [w["text"] for w in segment["words"]]
        if len(resynced) < len(segment["words"]):
            print("fulltext\n", fulltext)
            print("words\n", " ".join([w["text"] for w in segment["words"]]))
            print("Resync\n", " ".join([w["text"] for w in resynced]))
            print("BAD RESYNC, using original")
            resynced = segment["words"]
            # raise Exception("Bad resync, {} words, expected {}".format(len(resynced), len(segment["words"])))
        word_offset = 0
        start_ts = segment["start"]
        # while len(text) > max_chars or segment["end"] - start_ts > max_time:
        while word_offset < len(resynced):

            wordnr = word_offset + get_cut_point(segment["words"][word_offset:], max_time, max_chars)
            t = " ".join([s["text"] for s in segment["words"][word_offset:wordnr+1]])

            min_length = len(t) / 20.  # 20 chars pr second is quite fast
            new_segment = {
                "start": start_ts,
                    "end": max(resynced[wordnr]["end"], start_ts + min_length),
                "text": t
            }

            new_segments.append(new_segment)
            start_ts = new_segment["end"] #  # Better if this is immediately after (if it's a continuation)
            # If the previous char was some sort of stop, allow pause
            if word_offset > 0 and word_offset < len(resynced) and \
               resynced[word_offset - 1]["text"] and \
               resynced[word_offset - 1]["text"][-1] in [".", ",", "!", "?"]:
                  new_segment["start"] = resynced[word_offset]["start"]
            word_offset = wordnr + 1

    print("Converted %d segments to %d segments" % (len(segments), len(new_segments)))

    for s in new_segments:
      s["text"]: balance(s["text"], 40)

      # Sanity
      if s["end"] < s["start"]:
        raise Exception("Segment ends before it starts", s)

    return new_segments


def find_cutpoints(text, items="fullstop", maxlen=37):
    """
    Items can be "fullstop" for ".!?", pause for ",-:;" and "space" for whitespace
    """
    r = {"fullstop": "[\.\?\!] ", "pause": "[,:;] ", "stops": "[\.\?\!,:;] ", "space": "[\W]", "punctuation": "[\.?!,:;-]"}

    if items not in r:
        raise Exception("Bad cutpoint '%s'" % items)

    return [(match.start(), match.group()) for match in re.finditer(r[items], text[:maxlen] + " ")]

def balance(text, max_chars):
    """
    Ensure that the lines are of similar length
    """
    if not text:
        return text

    text = text.replace("  ", " ")

    #if len(text) < max_chars:
    #    return [trim(text)]

    mid_point = int(len(text) / 2)

    # Find the space before the mid point
    pos = text.rfind(" ", 0, mid_point)
    # If there is a full stop, use that
    m = int(mid_point * 0.6)
    if len(text) < max_chars:
        pos = len(text)

    c = find_cutpoints(text[m:int(mid_point * 1.6)], "stops")
    if c and c[0]:
        pos = m + c[0][0]

    if pos > -1 and pos < len(trim(text)) - 1:
        lines = [trim(text[:pos + 1]), trim(text[pos + 1:])]
    else:
        lines = [trim(text)]

    return lines

def trim(s):
    # Remove additional spaces, also spaces in front of punctuation
    import re

    while True:
        m = re.search("(\s[\W\s])", s)
        if not m:
            break
        s = s[:m.span()[0]] + s[m.span()[0] + 1:]
    return s.strip()

def sec2time(sec):
    h = int(sec // 3600)
    m = int((sec // 60) % 60)
    s = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def write_vtt(entries, filename, header="FILE"):
    with open(filename, "w") as f:
        f.write("WEBVTT %s\n\n" % header)

        counter = 1
        for entry in entries:
            f.write("%d\n" % counter)
            counter += 1
            f.write("%s --> %s\n" %
                    (sec2time(entry["start"]), sec2time(entry["end"])))

            if isinstance(entry["text"], list):
                for text in entry["text"]:
                    f.write("%s\n" % text)
            else:
                f.write(entry["text"] + "\n")
            f.write("\n")


def fix_overlap(segments, max_overlap=0.5):
    # We check if there is overlap between segments, and if it is just a little
    # (less than max_overlap) we just remove the overlap. Larger overlaps we
    # don't handle like this, it's probably a different error
    for idx, segment in enumerate(segments):
        if idx == 0:
            continue
        if segment["start"] < segments[idx - 1]["end"] and \
           segment["start"] < segments[idx - 1]["end"] + max_overlap:
            segments[idx - 1]["end"] = segments[idx]["start"]

    return segments


def process_task(cc, task):

    args = task["args"]
    src = args["src"]
    dst = args["dst"]
    basename = args.get("basename", None)
    fileformat = args.get("format", "vtt")

    if os.path.isdir(dst):
        # Create a new destination
        dst = os.path.join(dst, os.path.splitext(os.path.basename(src))[0]) + ".{}".format(fileformat)

    dst_dir = os.path.split(dst)[0]

    if basename:
        dst = os.path.join(dst_dir, basename + ".{}".format(fileformat))

    cc.log.debug("Destination directory '%s'" % dst_dir)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    max_chars = int(args.get("max_chars_per_line", 40))
    max_time = float(args.get("max_time_pr_sub",6.0))

    print("Processing", src)
    with open(src, "r") as f:
        subs = json.load(f)

    # Merge segments if they are the same speaker so we can re-split them better
    if "segments" in subs:
        subs = subs["segments"]

    new_segments = merge_segments(subs)

    # Split splits for maximum length, we don't want two full, long lines if possible
    new_segments = split_segments(new_segments, math.floor(max_chars * 1.5), max_time=max_time)

    new_subs = [{"start": s["start"], "end": s["end"], "text": balance(s["text"], 40)} for s in new_segments]

    new_subs = fix_overlap(new_subs)

    if dst.endswith(".json"):

        # new_subs has text as a list of lines, this should be newline separated text
        for sub in new_subs:
            sub["text"] = "\n".join(sub["text"])

        print("  Writing json subs", dst)
        with open(dst, "w") as f:
            json.dump(new_subs, f, indent=" ")
    else:
        print("  Writing vtt", dst)
        write_vtt(new_subs, dst)

    with open("/tmp/debug.json", "w") as f:
        json.dump(new_subs, f, indent=" ")

    return 100, {"dst": dst}



if __name__ == "__main__":
    import sys
    process_task(None, {"args": {"src": sys.argv[1], "dst": sys.argv[2]}})

