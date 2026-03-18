#!/usr/bin/env python3



"""Small helper to get/set YAML config values."""







import argparse



import os



import sys



from pathlib import Path







import yaml











def load(p: Path):



    if not p.exists():



        return {}



    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}











def save(p: Path, cfg):



    p.parent.mkdir(parents=True, exist_ok=True)



    p.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")











def get_path(cfg, path: str):



    cur = cfg



    for part in path.split("."):



        if not isinstance(cur, dict) or part not in cur:



            return None



        cur = cur[part]



    return cur











def set_path(cfg, path: str, value):



    cur = cfg



    parts = path.split(".")



    for part in parts[:-1]:



        if part not in cur or not isinstance(cur[part], dict):



            cur[part] = {}



        cur = cur[part]



    cur[parts[-1]] = value











def main():



    ap = argparse.ArgumentParser()



    ap.add_argument("--config", default=os.getenv("CONFIG_PATH", "/data/config.yaml"))



    sub = ap.add_subparsers(dest="cmd", required=True)







    ap_get = sub.add_parser("get")



    ap_get.add_argument("path")







    ap_set = sub.add_parser("set")



    ap_set.add_argument("path")



    ap_set.add_argument("value")



    ap_set.add_argument("--type", choices=["str", "int", "bool", "json", "list"], default="str")







    ap_add = sub.add_parser("add_source")



    ap_add.add_argument("name")



    ap_add.add_argument("rss_url")







    ap_del = sub.add_parser("del_source")



    ap_del.add_argument("name")







    sub.add_parser("list_sources")







    args = ap.parse_args()







    from json import loads as json_loads







    p = Path(args.config)



    cfg = load(p)







    if args.cmd == "get":



        v = get_path(cfg, args.path)



        if v is None:



            sys.exit(1)



        if isinstance(v, (dict, list)):



            print(yaml.safe_dump(v, sort_keys=False, allow_unicode=True).strip())



        else:



            print(v)



        return







    if args.cmd == "set":



        if args.type == "int":



            val = int(args.value)



        elif args.type == "bool":



            val = args.value.lower() in ("1", "true", "yes", "y", "on")



        elif args.type == "json":



            val = json_loads(args.value)



        elif args.type == "list":



            val = [x.strip() for x in args.value.split(",") if x.strip()]



        else:



            val = args.value



        set_path(cfg, args.path, val)



        save(p, cfg)



        print("OK")



        return







    if args.cmd == "add_source":



        cfg.setdefault("sources", [])



        cfg["sources"] = [s for s in cfg["sources"] if (s or {}).get("name") != args.name]



        cfg["sources"].append({"name": args.name, "rss_url": args.rss_url})



        save(p, cfg)



        print("OK")



        return







    if args.cmd == "del_source":



        cfg.setdefault("sources", [])



        before = len(cfg["sources"])



        cfg["sources"] = [s for s in cfg["sources"] if (s or {}).get("name") != args.name]



        save(p, cfg)



        print(before - len(cfg["sources"]))



        return







    if args.cmd == "list_sources":



        for s in cfg.get("sources", []) or []:



            print(f"{s.get('name')}\t{s.get('rss_url')}")



        return











if __name__ == "__main__":



    main()