import argparse
import re



class SubParser:
    """Parse VTT/SRT files."""

    def __init__(self):
        self.items = []

    @staticmethod
    def time2sec(t):
        ms = t.split(",")[1]
        t = t[:-len(ms) - 1]
        if t.count(":") == 2:
            h, m, s = t.split(":")
        else:
            m, s = t.split(":")
            h = 0
        ts = int(h) * 3600 + int(m) * 60 + int(s) + (int(ms) / 1000.)
        return ts

    def load_srt(self, filename, default_who=None):
        with open(filename, "rb") as f:

            start = end = None
            text = ""

            for line in f.readlines():
                line = line.decode("utf-8").strip()
                if text and line.startswith("-"):
                    # print("Continuation", line)
                    s = {
                        "start": SubParser.time2sec(start) + 0.01,
                        "end": SubParser.time2sec(end),
                        "text": line[1::].strip()}
                    if default_who:
                        s["who"] = default_who
                    self.items.append(s)
                    # text = ""
                    continue
                elif line.startswith("-"):
                    line = line[1:]

                if line.strip() == "":
                    # print("End of comment", text)
                    # End of comment
                    if text and start and end:
                        s = {
                            "start": SubParser.time2sec(start),
                            "end": SubParser.time2sec(end),
                            "text": text
                        }
                        if default_who:
                            s["who"] = default_who

                        self.items.append(s)
                    start = end = None
                    text = ""
                    continue
                if re.match("^\d+$", line):
                    # Just the index, we don't care
                    continue

                m = re.match("(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)", line.replace(".", ","))
                if not m:
                    m = re.match("(\d+:\d+,\d+) --> (\d+:\d+,\d+)", line.replace(".", ","))
                if m:
                    start, end = m.groups()
                    continue

                # print("TEXT", text, "LINE", line)
                if text and text[-1] != "-":
                    text += "<br>"
                    text += line
                else:
                    text = text[:-1] + line  # word has been divided

        return self.items



def load_vtt_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    captions = []
    for i in range(len(lines)):
        if re.match(r'^\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}', lines[i]):
            caption = {}
            caption['start'] = lines[i].split(' --> ')[0]
            caption['end'] = lines[i].split(' --> ')[1].strip()
            caption['text'] = ''
            j = i + 1
            while j < len(lines) and lines[j].strip() != '':
                caption['text'] += lines[j].strip() + ' '
                j += 1
            captions.append(caption)
    return captions

def load_rttm_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    speakers = []
    for line in lines:
        if line.startswith('SPEAKER'):
            parts = line.strip().split()
            speakers.append({
                'start': float(parts[3]),
                'end': float(parts[3]) + float(parts[4]),
                'speaker': parts[7]
            })
    return speakers

def create_dictionary(vtt_file_path, rttm_file_path):
    parser = SubParser()
    captions = parser.load_srt(vtt_file_path)
    speakers = load_rttm_file(rttm_file_path)
    result = []
    for caption in captions:
        speaker = 'unknown'
        max_overlap = 0
        for spk in speakers:
            overlap = min(float(spk['end']) - float(caption['start']), float(caption['end']) - float(spk['start']))
            if overlap > max_overlap:
                max_overlap = overlap
                speaker = spk['speaker']
        result.append({
            'start': caption['start'],
            'end': caption['end'],
            'speaker': speaker,
            'text': caption['text']
        })
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create a dictionary from VTT and RTTM files')
    parser.add_argument('vtt_file', type=str, help='Path to the VTT file')
    parser.add_argument('rttm_file', type=str, help='Path to the RTTM file')
    args = parser.parse_args()

    dictionary = create_dictionary(args.vtt_file, args.rttm_file)
    import json
    # print(json.dumps(dictionary, indent=4))

    for item in dictionary:
        print(item['speaker'], item['text'])

