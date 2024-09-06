#!/usr/bin/env python3

import json
import random


def merge_persons(sources, destination, max_samples=15):
    """
    Merges multiple person JSON files into a single person JSON file.
    The destination file will contain all the samples from all the sources.
    """
    person = {}

    # Load the sources and merge them into the destination
    for src in sources:
        with open(src) as f:
            src_person = json.load(f)
            if not person:
                person = src_person
                continue

            if not src_person["stable"]:
                print("Skipping unstable person", src_person["id"])
                continue
 
            person["audio_samples"].extend(src_person["audio_samples"])
            if not src_person["name"].startswith("Speaker"):
                person["name"] = src_person["name"]
                person["id"] = src_person["id"]

    print("Num embeddings", len(person["embeddings"]))
    del person["samples"]
    del person["embeddings"]
    del person["count"]

    print("Number of total samples:", len(person["audio_samples"]))

    # We remove the short ones
    person["audio_samples"] = [s for s in person["audio_samples"] if len(s) > 48000]

    print("Number of large samples:", len(person["audio_samples"]))

    # We pick the maximum allowed randomly
    person["audio_samples"] = random.sample(person["audio_samples"],
                                            min(max_samples, len(person["audio_samples"])))

    print("Number of final samples:", len(person["audio_samples"]))
    print("Size of samples: min/max/avg", min(len(s) for s in person["audio_samples"]),
          max(len(s) for s in person["audio_samples"]),
          sum(len(s) for s in person["audio_samples"]) / len(person["audio_samples"]))

    # Save the merged person
    with open(destination, "w") as f:
        json.dump(person, f, indent=4)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('sources', nargs='+', help='JSON files to merge')
    parser.add_argument('-o', '--output', help='Destination JSON file')
    parser.add_argument('--max-samples', type=int, default=15,
                        help='Maximum number of samples to keep')

    args = parser.parse_args()

    merge_persons(args.sources, args.output, args.max_samples)

    print("Saved to", args.output)
