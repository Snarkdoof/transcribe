import os
import requests
import json
import sys
import tempfile
import re
import time
import queue
import threading


ccmodule = {
    "description": "Annotate texts and identify cards/info",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "Subtitle file (json)",
        "url": "Service URL for lookup",
        "dst": "Destination file (json)",
        "lang": "Language (xx.wikipedia.com) for lookups"
    },
    "outputs": {
        "dst": "Destination card file"
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


class Lookup:
    def __init__(self, subfile, lookup_url, log, lang="no"):
        self.lookup_url = lookup_url
        self.log = log
        self.lang = lang

        with open(subfile, "r") as f:
            self.subs = json.load(f)

        self.stopwords = self._load_stopwords("https://seer2.itek.norut.no/stopwords_combined.txt")

        self.keywords = []

        self.stop_event = threading.Event()
        self.inqueue = queue.Queue()

        lookup_thread = threading.Thread(target=self.lookup_ai)
        lookup_thread.start()
        self.check_cards()

    def save(self, filename):
        with open(filename, "wb") as f:
            f.write(json.dumps(self.keywords, indent=" ").encode("utf-8"))

    def _load_stopwords(self, uri):
        if uri.startswith("http"):
            r = requests.get(uri)
            words = r.text
        else:
            words = open(filename, "rb").read().decode("latin-1")
        return words.split("\n")

    def build_card(self, item):
        if not item or "type" not in item:
            return ""

        if item["type"] == "LOC":
            key  = "AIzaSyAFI-Pk-PzIfjPGqmNO6qGQw_m0Cr3NV3I";
            print("Might want to check Google Maps")
            url = "https://www.google.com/maps/embed/v1/place?key=%s&q=" % key + " ".join(item["keywords"])
            return url

        keywords = item["keywords"]

        url = "https://%s.wikipedia.org/w/index.php?search=" % self.lang 
        url += " ".join(keywords) + "&title=Spesial%3AS%C3%B8k&go=G%C3%A5&ns0=1"

        r = requests.get(url)
        if r.status_code < 300:
            m = re.search('\<link rel="canonical" href="([^\"]+)"', r.text)
            if m:
                new_url = m.groups()[0]

                if new_url.find("search") > -1:
                    return None

                return new_url

            if r.text.find("<title>Søkeresultater") > -1:
                return None

            return url

    def check_cards(self):
        """
        Go through all detections and check for "cards"
        """

        self.cards = {}  # Find these somewhere else?

        # Go through all detections and see if we might have one from before
        # If not, check if we can create a new card

        while True:
            item = {}
            try:
                item = self.inqueue.get(timeout=1.0)
                if not item:
                    print("No item in time, stopping")
                    break
            except queue.Empty:
                # Queue is empty and the AI is done
                if self.stop_event.is_set():
                    break

            if "type" not in item:
                self.log.error("Bad item, expected 'type' as key: %s" % str(item))
                continue

            if item["type"] not in self.cards:
                self.cards[item["type"]] = []

            found = False
            for keyword in item["keywords"][0].split(" "):
                for card in self.cards[item["type"]]:
                    for ckw in card["keywords"][0].split(" "):
                        if keyword.startswith(ckw) or ckw.startswith(keyword):
                            found = card
                            break
                    if found:
                        break
                if found:
                    break

            if not found:
                print("Must create a card for", item["keywords"])
                card = {
                    "keywords": item["keywords"],
                    "type": item["type"]
                }
                url = self.build_card(item)
                if (url):
                    card["url"] = url
                self.cards[item["type"]].append(card)
                found = card

            else:
                print("Recycle:", found)

            if found:
                item["card"] = found
            self.keywords.append(item)

    def lookup_ai(self, subs=None):
        if not subs:
            subs = self.subs

        for sub in subs:
            t = sub["text"].replace("<br>", " ").replace("-", " ")
            if t.count(" ") < 6:
                continue  # Need some words for the AI to work

            interesting = self._sat(t)
            for entry in interesting:
                self.log.info("Interesting entry '%s'" % str(entry))
                print("Interesting entry", entry)
                self.inqueue.put({
                    "start": sub["start"],
                    "end": sub["end"],
                    "keywords": [entry["word"]],
                    "type": entry["entity_group"],
                    "score": entry["score"]
                    })

        self.stop_event.set()

    def _sat(self, text):
        # url = "https://api-inference.huggingface.co/models/saattrupdan/nbailab-base-ner-scandi"

        args = {"inputs": text, "parameters": {"aggregation_strategy": "first"}}

        r = requests.post(self.lookup_url, json.dumps(args).encode("utf-8"))
        if r.status_code != 200:
            raise Exception("Failed to look up, code %s" % r.status_code)

        try:
            res = json.loads(r.text)
        except Exception as e:
            print("BAD REPLY", r.text)
            raise e

        if "error" in res:
            print("Error", res)
            if "estimated_time" in res:
                time.sleep(res["estimated_time"] + 1.0)
                return self._sat(text)
            raise Exception("Failed: " + r.text)

        # If we have multiple names close to each other, we regard them as one?
        r = []
        if not isinstance(res, list):
            res = [res]
        for i, entity in enumerate(res):
            if entity == {}:
                continue

            if i == 0:
                r.append(entity)
                continue  # Can't group one

            if entity["entity_group"] == "PER" and res[i - 1]["entity_group"] == "PER":
                if entity["start"] - res[i - 1]["end"] <= 1:
                    r[-1]["word"] += " " + entity["word"]
                    r[-1]["end"] = entity["end"]
                    continue
            r.append(entity)

        return r


def process_task(cc, task):

    args = task["args"]
    service_url = args.get("url", "https://seer3.itek.norut.no/sat")
    subs = args.get("src")
    dst = args.get("dst", subs.replace("_subs.json", "_cards.json"))
    lang = args.get("lang", "no")

    lookup = Lookup(subs, service_url, cc.log, lang=lang)
    lookup.check_cards()
    lookup.save(dst)

    return 100, {"dst": dst}
