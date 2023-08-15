#!/usr/bin/env python3 
import extcolors
import json
import requests
import tempfile
import os
import random


class Palette:

    def random_color(self):
        return "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])

    def process_file(self, src, dst, image, opacity=0xA6, replace=False):
        if image and image.startswith("http"):

            r = requests.get(image)
            if r.status_code != 200:
                raise Exception("Failed to get '%s': %s" % (image, r.status_code))    

            t = tempfile.mktemp()

            with open(t, "wb") as f:
                f.write(r.content)

            colors, pixel_count = extcolors.extract_from_path(t)
            os.remove(t)
        elif image:
            colors, pixel_count = extcolors.extract_from_path(image)
        else:
            colors = []

        c = []
        for color in colors:
            clr = [x + 40 if x < 60 else x for x in color[0]]
            print("CLR", clr)
            c.append(("#%02x%02x%02x" % tuple(clr)) + "%02x" % opacity)

        # We now go through the cast and add colors

        with open(src, "r") as f:
            cast = json.load(f)

        if len(cast) > len(c):
            print("Not enough colors, %d > %d, generating" % (len(cast), len(c)))

        while len(cast) > len(c):
            c.append(self.random_color() + "%02x" % opacity)

        # If we already have a color in use, don't use it
        for person in cast.values():
            print("Checking cast", person)
            if "color" in person:
                if person["color"] in c:
                    print("Removing", person["color"])
                    c.remove(person["color"])

        idx = 0
        for person in cast:
            if isinstance(cast[person], list):
                continue
            if "color" not in cast[person] or cast[person]["color"] == "#ffeeffA6":
                cast[person]["color"] = c[idx % len(c)]
                idx += 1

        if replace:
            os.rename(src, src + ".bak")
            dst = src

        if len(c) > len(cast):
            cast["extras"] = c[len(cast):]

        if dst:
            with open(dst, "w") as f:
                json.dump(cast, f, indent=" ")

        return cast


if __name__ == "__main__":

    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("-c", "--cast", dest="cast", help="Cast file", required=True)
    parser.add_argument("-i", "--image", dest="image", help="Image file for colors - random if not given", required=False)
    parser.add_argument("--opacity", dest="opacity", help="Default opacity", default=166)
    parser.add_argument("-o", "--output", dest="dst", help="Destination file")

    parser.add_argument("-r", "--replace", dest="replace", action="store_true", default=False,
                        help="Overwrite original cast (rename to .bak)")

    options = parser.parse_args()

    palette = Palette()
    c = palette.process_file(options.cast, options.dst, options.image, options.opacity, options.replace)

    if not options.dst:
        print(c)
