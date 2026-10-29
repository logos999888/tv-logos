"""Build a merged XMLTV guide: the IPTV provider's guide with channel logos from this repo.

TiviMate only shows an EPG logo for a channel when that same EPG source also supplies the
channel's programmes. So this script republishes the provider's guide with our logos swapped in:

* channels whose EPG id has programmes get our logo on the provider's <channel> entry;
* channels with no programmes get their own entry, keyed by channel name (TiviMate matches by
  name when the id doesn't match), with a placeholder programme per day so TiviMate uses it.

Provider login comes from environment variables (GitHub secrets) and is never printed or written
to the output. For a local test run, pass --streams and --xmltv files instead.
"""
import argparse
import collections
import gzip
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape, quoteattr

# TiviMate looks up logo files by channel name with characters that are unsafe in file names
# replaced, so compare names with all of those (and "_") folded to one character.
UNSAFE = re.compile(r'[/:*?"<>\\|_]')
PLACEHOLDER_DAYS = range(-1, 8)


def norm(name):
    return re.sub(r"\s+", " ", UNSAFE.sub("_", name)).strip().casefold()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = resp.read()
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def provider_data(args):
    if args.streams and args.xmltv:
        with open(args.streams, "rb") as f:
            streams = f.read()
        with open(args.xmltv, "rb") as f:
            xmltv = f.read()
        return json.loads(streams), xmltv
    host = os.environ["XTREAM_HOST"].rstrip("/")
    auth = urllib.parse.urlencode({"username": os.environ["XTREAM_USER"], "password": os.environ["XTREAM_PASS"]})
    try:
        streams = json.loads(fetch(f"{host}/player_api.php?{auth}&action=get_live_streams"))
        xmltv = fetch(f"{host}/xmltv.php?{auth}")
    except Exception as e:
        # The exception text can contain the request URL, and with it the login
        sys.exit(f"Download from the provider failed ({type(e).__name__})")
    if not isinstance(streams, list):
        sys.exit("Provider did not return a channel list (check the login secrets)")
    return streams, xmltv


def element_xml(el):
    return ET.tostring(el, encoding="unicode")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--streams")
    ap.add_argument("--xmltv")
    ap.add_argument("--logos", default="logos.json")
    ap.add_argument("--base-url", default=os.environ.get("LOGO_BASE_URL", ""))
    ap.add_argument("--out", default="site/epg.xml.gz")
    ap.add_argument("--report", default="site/report.json")
    args = ap.parse_args()

    with open(args.logos, encoding="utf-8") as f:
        logos = json.load(f)
    by_norm = {norm(k): v for k, v in logos.items()}
    streams, xmltv = provider_data(args)

    # Playlist channel name -> (logo image, EPG id)
    wanted = {}
    for s in streams:
        name = (s.get("name") or "").strip()
        img = logos.get(name) or by_norm.get(norm(name))
        if name and img:
            wanted[name] = (img, (s.get("epg_channel_id") or "").strip())

    channels, programmes = {}, collections.defaultdict(list)
    for _, el in ET.iterparse(io.BytesIO(xmltv)):
        if el.tag == "channel":
            channels[el.get("id")] = el
        elif el.tag == "programme":
            programmes[el.get("channel")].append(element_xml(el))
            el.clear()

    # Several playlist channels (HD/FHD/backup) can share one EPG id; use their most common logo
    id_logos = collections.defaultdict(collections.Counter)
    no_guide = []
    for name, (img, epg_id) in wanted.items():
        if epg_id and programmes.get(epg_id):
            id_logos[epg_id][img] += 1
        else:
            no_guide.append(name)

    url = lambda img: f"{args.base_url.rstrip('/')}/images/{img}"
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="tv-logos">\n')
        for cid, el in channels.items():
            if cid in id_logos:
                for icon in el.findall("icon"):
                    el.remove(icon)
                ET.SubElement(el, "icon", src=url(id_logos[cid].most_common(1)[0][0]))
            out.write(element_xml(el).strip() + "\n")
        for name in no_guide:
            out.write(f"<channel id={quoteattr(name)}><display-name>{escape(name)}</display-name>"
                      f"<icon src={quoteattr(url(wanted[name][0]))}/></channel>\n")
        for items in programmes.values():
            out.writelines(p.strip() + "\n" for p in items)
        for name in no_guide:
            for d in PLACEHOLDER_DAYS:
                start = (today + timedelta(days=d)).strftime("%Y%m%d%H%M%S +0000")
                stop = (today + timedelta(days=d + 1)).strftime("%Y%m%d%H%M%S +0000")
                out.write(f"<programme start={quoteattr(start)} stop={quoteattr(stop)} channel={quoteattr(name)}>"
                          f"<title>{escape(name)}</title></programme>\n")
        out.write("</tv>\n")

    matched_norm = {norm(n) for n in wanted}
    report = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "playlist_channels": len(streams),
        "channels_with_logo": len(wanted),
        "with_provider_guide": len(wanted) - len(no_guide),
        "logo_only_entries": len(no_guide),
        "logo_names_not_in_playlist": sorted(k for k in logos if norm(k) not in matched_norm),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print({k: v for k, v in report.items() if k != "logo_names_not_in_playlist"},
          "logo_names_not_in_playlist:", len(report["logo_names_not_in_playlist"]))


if __name__ == "__main__":
    main()
