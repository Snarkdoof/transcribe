#!/usr/bin/env python3

import json
import base64
import pickle
import os.path


def replace_norwegian_chars(input_str):
    norwegian_chars = "æøåÆØÅ "
    ascii_chars = "aoeAOE_"

    # Create a mapping from norwegian characters to ascii characters
    char_map = {norwegian_chars[i]: ascii_chars[i] for i in range(len(norwegian_chars))}

    # Use translate method to replace characters in the input string
    return input_str.translate(str.maketrans(char_map))


def process_file(vc, options):
    with open(options.src, "r") as f:
        people = json.load(f)

    destinations = []

    for id in people:
        person = people[id]
        print("Processing %s (%s)" % (id, person["name"]))
        newperson = {}

        for key in ["name", "src", "color"]:
            if key in person:
                newperson[key] = person[key]

        # The voice
        embeddings = []
        for segment in person["segments"]:        
            for time in segment["times"]:
                e = vc.get_embedding(options.audiofile, time[0], time[1])
                embeddings.append(e)

        newperson["voice"] = base64.b64encode(pickle.dumps(embeddings)).decode("ascii")

        # Target file
        name = replace_norwegian_chars(person["name"])
        if not options.dst:
            dst = os.path.expanduser("~/peopleDB/%s.json" % name)
        else:
            dst = os.path.join(options.dst, "%s.json" % name)
        destinations.append(dst)

        if os.path.exists(dst):
            print("  ERROR: File already exists: '%s'" % dst)
            continue

        with open(dst, "w") as f:
            json.dump(newperson, f, indent=" ")

        print("Saved to", dst)
    return destinations

if __name__ == "__main__":

    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("-n", "--name", dest="name", help="Name")
    parser.add_argument("-s", "--src", dest="src", help="Source file if multiple people")
    parser.add_argument("-c", "--color", dest="color", help="Color, leave for automatic")
    parser.add_argument("-f", "--file", dest="audiofile", help="Source audio file", required=True)
    parser.add_argument('times', type=str, nargs='*', help="Times, format start-end e.g. 1.0-5.2")
    parser.add_argument("-d", "--dest", dest="dst", help="Destination", required=False)
    parser.add_argument("-a", "--avatar", dest="avatar", help="Avatar img")

    options = parser.parse_args()

    if not options.name and not options.src:
        raise SystemExit("Need either a name or a file with multiple people")

    from modules.mod_speaker_identification2 import VoiceCompare
    vc = VoiceCompare(None)
    vc._load_model()

    if options.src:
        destinations = process_file(vc, options)
        print(" - OK")
        print(json.dumps(destinations))
        raise SystemExit()

    embeddings = []
    for t in options.times:
        start, end = tuple([float(x) for x in t.split("-")])

        e = vc.get_embedding(options.audiofile, start, end)
        embeddings.append(e)

    person = {
        "name": options.name
    }
    if options.color:
        person["color"] = options.color
    if options.avatar:
        person["src"] = options.avatar

    # If we don't have a destination, put it under  ~/peopleDB/name.json
    # where " " is replaced with "_"
    if not options.dst:
        options.dst = os.path.expanduser("~/peopleDB/%s.json" % options.name.replace(" ", "_"))

    # Encode embeddings
    person["voice"] = base64.b64encode(pickle.dumps(embeddings)).decode("ascii")

    with open(options.dst, "w") as f:
        json.dump(person, f)


# kjersti_mjor: 144.5-148.5 218-224
# odd_drevland: 226-232 234.7-237.8
# ./create_person.py -n "Kjesti Mjor" -f /tmp/OddDrevland_1_3_mono.wav -d /home/njaal-local/peopleDB/kjersti_mjor.json -a "/hack/datasets/gfx/kjersti_mjor.png" 144.5-148.5 218-224
# ./create_person.py -n "Odd Drevland" -f /tmp/OddDrevland_1_3_mono.wav -d /home/njaal-local/peopleDB/odd_drevland.json -a "/hack/datasets/gfx/kjersti_mjor.png" 226-232 234.7-237.8

# ./create_person.py -n "Graham Norton" -f /tmp/buxton_188_mono.wav -d /home/njaal-local/peopleDB/graham_norton.json -a "/hack/datasets/gfx/graham_norton.png"  720-730


# ./create_person.py -n "Hedwig Montomery" -f /tmp/larerens_time_mono.wav -d /home/njaal-local/peopleDB/Hedwig_Montomery.json -a "/hack/datasets/gfx/Hedwig_Montgomery.png"  75.41-82.41 194.66-199.66
# ./create_person.py -n "Tonje Steinsland" -f /tmp/larerens_time_mono.wav -d /home/njaal-local/peopleDB/Tonje_Steinsland.json -a "/hack/datasets/gfx/Tonje_Steinsland.png" 176.03-182.53 183.56-188.56
