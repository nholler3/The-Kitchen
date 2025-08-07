#!/usr/bin/env python3
import os, sys, json, argparse, requests, shutil

API_BASE = "https://api.curseforge.com/v1"

def load_project_ids(path):
    with open(path, "r") as f:
        data = json.load(f)
    # Accept either a manifest.json or a simple list
    if isinstance(data, dict) and "files" in data:     # CurseForge manifest.json
        return [x["projectID"] for x in data["files"]]
    if isinstance(data, list):                          # simplified [{projectID: ...}, ...] or [123, 456]
        if all(isinstance(x, dict) for x in data):
            return [x["projectID"] for x in data]
        if all(isinstance(x, int) for x in data):
            return data
    raise SystemExit("Unrecognized input JSON format. Provide manifest.json or a list of projectIDs.")

def pick_latest_release(files, mc_ver, loader, allow_beta=False):
    # releaseType: 1=release, 2=beta, 3=alpha
    def ok(f, allow_prerelease):
        gv = set((f.get("gameVersions") or []))
        # match MC version and loader tag
        if mc_ver not in gv: return False
        if loader and loader not in gv: return False
        rt = f.get("releaseType", 3)
        if allow_prerelease:
            return rt in (1,2)  # release or beta
        return rt == 1          # releases only

    # Try strict (release only), then fallback (beta allowed) if requested
    candidates = [f for f in files if ok(f, allow_prerelease=False)]
    if not candidates and allow_beta:
        candidates = [f for f in files if ok(f, allow_prerelease=True)]
    # Sort newest first by fileDate
    candidates.sort(key=lambda f: f.get("fileDate",""), reverse=True)
    return candidates[0] if candidates else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="infile",  required=True, help="manifest.json or list of projectIDs")
    ap.add_argument("--out", dest="outdir",  required=True, help="staging dir to write jars")
    ap.add_argument("--mc",  dest="mcver",   default="1.20.1", help="Minecraft version (e.g. 1.20.1)")
    ap.add_argument("--loader", dest="loader", default="Forge", choices=["Forge","NeoForge",""], help="Match loader tag")
    ap.add_argument("--allow-beta", action="store_true", help="Allow beta if no release matches")
    args = ap.parse_args()

    api_key = os.environ.get("CURSEFORGE_API_KEY")
    if not api_key:
        raise SystemExit("Missing CURSEFORGE_API_KEY env var")
    headers = {"x-api-key": api_key}

    proj_ids = load_project_ids(args.infile)
    os.makedirs(args.outdir, exist_ok=True)

    # Clean stage first (only jars)
    for name in os.listdir(args.outdir):
        if name.endswith(".jar"):
            os.remove(os.path.join(args.outdir, name))

    for pid in proj_ids:
        # Pull file list (page size big enough for recent versions)
        url = f"{API_BASE}/mods/{pid}/files?pageSize=50"
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        files = r.json().get("data", []) or []

        chosen = pick_latest_release(files, args.mcver, args.loader, args.allow_beta)
        if not chosen or not chosen.get("downloadUrl"):
            print(f"[WARN] No matching file for project {pid} (mc={args.mcver}, loader={args.loader})")
            continue

        name = chosen["fileName"]
        dl = chosen["downloadUrl"]
        print(f"Downloading {name}")
        with requests.get(dl, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            with open(os.path.join(args.outdir, name), "wb") as out:
                shutil.copyfileobj(resp.raw, out)

    print("Done.")

if __name__ == "__main__":
    main()
