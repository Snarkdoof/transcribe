import json
import subprocess
import base64
import tempfile
import wave


def ffplay_segment(filename):

    subprocess.run([
        'ffplay',
        '-autoexit',
        '-i', filename
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(args):
    for src in args.src:
        print(src)
        with open(src) as f:
            person = json.load(f)

        print("*********************\nPlaying segments for", person['id'],
              "stable" if person["stable"] else "unstable")

        if len(person["audio_samples"]) != len(person["samples"]):
            print("Number of audio samples and samples don't match")
            print(len(person["audio_samples"]), len(person["samples"]))

        # for idx, sample in enumerate(person["samples"]):
        #    start, end, confidence = sample

        for audio_sample in person["audio_samples"]:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                data = base64.b64decode(audio_sample)
                with wave.open(f, 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(data)
                ffplay_segment(f.name)
                input()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    # parser.add_argument('audio_file', help='Audio file to play segments from')
    parser.add_argument('src', nargs='+', help='JSON file containing the person with samples')

    main(parser.parse_args())