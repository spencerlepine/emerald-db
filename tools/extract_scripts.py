"""Event scripts and text: every .string in the overworld script files, every
script label with what it does (flags, vars, items, Pokémon, trainers, warps,
movement), and dialogue attributed to the NPC / sign / trigger that runs it.

Sources: data/event_scripts.s, data/maps/*/scripts.inc, data/scripts/*.inc,
data/text/*.inc, include/constants/flags.h, include/constants/vars.h.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from common import SRC, clean_text, entity, read, read_csv, rel, slug, strip_c_comments, DATABASE_DIR
from extract_maps import map_id, npc_id
from extract_pokemon import iid, sid
from extract_trainers import trid

LABEL = re.compile(r"^([A-Za-z_]\w*)::?\s*(.*)$")
SPEAKER = re.compile(r"^((?:[A-Z][A-Z0-9.'&é\- ]{1,24}|\{[A-Z_0-9]+\}|\{STR_VAR_\d\}))\s*:\s+")
MOVEMENT_CMD = re.compile(r"^(walk|face|delay|jump|slide|step_end|emote|set_|lock_facing|unlock_facing|player_run|fly|disable|enable|nurse|walk_in_place|ride|init_affine|clear_fixed|figure|levitate|store_lock|hide|show|start_anim|rayquaza|destroy|acro|walk_slow|exclamation|heart|question|reveal|look_around|lock_anim|unlock_anim|copy|restore|walk_fast)")

FLAG_CMDS = {"setflag": "set", "clearflag": "clear", "checkflag": "check", "goto_if_set": "check", "goto_if_unset": "check",
             "call_if_set": "check", "call_if_unset": "check", "settrainerflag": "set", "cleartrainerflag": "clear"}
VAR_SET_CMDS = {"setvar", "addvar", "subvar", "copyvar"}
VAR_CHECK_CMDS = {"compare", "goto_if_eq", "goto_if_ne", "goto_if_lt", "goto_if_ge", "goto_if_le", "goto_if_gt",
                  "call_if_eq", "call_if_ne", "call_if_lt", "call_if_ge", "call_if_le", "call_if_gt", "switch"}
ITEM_CMDS = {"giveitem": "gives", "finditem": "gives", "additem": "gives", "removeitem": "takes", "checkitem": "checks",
             "checkitemspace": "checks", "giveitem_msg": "gives", "bufferitemname": "mentions", "givedecoration": "gives",
             "adddecoration": "gives", "addpcitem": "gives"}
MON_CMDS = {"givemon": "gives", "giveegg": "gives", "setwildbattle": "battles", "playmoncry": "cry", "bufferspeciesname": "mentions",
            "checkspecies": "checks", "seteventmon": "gives"}


def script_files() -> list[tuple[str, str]]:
    """[(relative path, owning map const or '')]."""
    out = [("data/event_scripts.s", "")]
    folder_to_const = {}
    for p in sorted((SRC / "data/maps").glob("*/map.json")):
        folder_to_const[p.parent.name] = json.loads(p.read_text())["id"]
    for p in sorted((SRC / "data/maps").glob("*/scripts.inc")):
        out.append((str(p.relative_to(SRC)), folder_to_const.get(p.parent.name, "")))
    for d in ("data/scripts", "data/text"):
        for p in sorted((SRC / d).glob("*.inc")):
            out.append((str(p.relative_to(SRC)), ""))
    return out


def parse_file(rel_path: str) -> list[dict]:
    """Split a script file into label blocks: {label, line, lines: [(lineno, text)]}."""
    blocks, cur = [], None
    for n, raw in enumerate(read(rel_path).splitlines(), 1):
        line = raw.split("@", 1)[0].rstrip() if '"' not in raw else _strip_at_comment(raw)
        if not line.strip():
            continue
        if line.strip().startswith(("#", ".include", ".set", ".align", ".section", ".global")):
            continue
        m = LABEL.match(line)
        if m and not line.startswith((" ", "\t")):
            cur = {"label": m.group(1), "line": n, "lines": [], "global": "::" in line}
            blocks.append(cur)
            rest = m.group(2).strip()
            if rest:
                cur["lines"].append((n, rest))
            continue
        if cur is not None:
            cur["lines"].append((n, line.strip()))
    return blocks


def _strip_at_comment(raw: str) -> str:
    out, inq = [], False
    for c in raw:
        if c == '"':
            inq = not inq
        if c == "@" and not inq:
            break
        out.append(c)
    return "".join(out).rstrip()


def extract() -> dict[str, list[dict]]:
    texts, scripts, dialogue, flags_rows, entities, rels = [], [], [], [], [], []
    text_by_label: dict[str, dict] = {}
    script_by_label: dict[str, dict] = {}

    for rel_path, map_const in script_files():
        for b in parse_file(rel_path):
            strings = [l for _, l in b["lines"] if l.startswith((".string", ".braille"))]
            if strings:
                raw = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', " ".join(strings)))
                clean = clean_text(raw)
                m = SPEAKER.match(clean)
                t = {"text_id": b["label"], "map_id": map_id(map_const) if map_const else "", "source_file": rel_path,
                     "source_line": b["line"], "speaker_label": m.group(1).strip() if m else "",
                     "braille": "true" if strings[0].startswith(".braille") else "false",
                     "text": clean, "text_raw": raw, "used_by_scripts": "", "word_count": len(clean.split()),
                     "text_origin": "script", "text_context": "map" if map_const else rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]}
                texts.append(t)
                text_by_label[b["label"]] = t
                continue
            cmds = [_split_cmd(l) for _, l in b["lines"]]
            cmds = [c for c in cmds if c[0]]
            if not cmds:
                continue
            kind = "movement" if all(MOVEMENT_CMD.match(c[0]) for c in cmds) else (
                "map_scripts" if any(c[0].startswith("map_script") for c in cmds) or b["label"].endswith("_MapScripts") else
                "data" if all(c[0].startswith(".") for c in cmds) else "script")
            s = {"script_id": b["label"], "map_id": map_id(map_const) if map_const else "", "source_file": rel_path,
                 "source_line": b["line"], "kind": kind, "commands": len(cmds), "_cmds": cmds}
            scripts.append(s)
            script_by_label[b["label"]] = s

    # ---- analyse script commands ---------------------------------------------------
    flag_use = defaultdict(lambda: defaultdict(set))
    var_use = defaultdict(lambda: defaultdict(set))
    trainer_texts = []
    for s in scripts:
        if s["kind"] != "script" and s["kind"] != "map_scripts":
            continue
        acc = defaultdict(list)
        for cmd, args in s["_cmds"]:
            for a in args:
                if a in text_by_label:
                    acc["texts"].append(a)
                elif a in script_by_label and a != s["script_id"]:
                    target = script_by_label[a]
                    acc["movements" if target["kind"] == "movement" else "jumps"].append(a)
            if cmd in FLAG_CMDS and args:
                acc["flags_" + FLAG_CMDS[cmd]].append(args[0])
                flag_use[args[0]][FLAG_CMDS[cmd]].add(s["script_id"])
            if cmd in VAR_SET_CMDS and args:
                acc["vars_set"].append(f"{args[0]}={args[1] if len(args) > 1 else ''}")
                var_use[args[0]]["set"].add(s["script_id"])
            if cmd in VAR_CHECK_CMDS and args and args[0].startswith("VAR_"):
                acc["vars_checked"].append(f"{args[0]}{'==' + args[1] if len(args) > 1 else ''}")
                var_use[args[0]]["check"].add(s["script_id"])
            if cmd in ITEM_CMDS and args and args[0].startswith(("ITEM_", "DECOR_")):
                acc["items_" + ITEM_CMDS[cmd]].append(args[0])
            if cmd in MON_CMDS and args and args[0].startswith("SPECIES_"):
                acc["species_" + MON_CMDS[cmd]].append(args[0])
            if cmd == "trainerbattle" and args and args[0].startswith("TRAINER_BATTLE_"):
                args = args[1:]
            if cmd.startswith("trainerbattle") and args and not args[0].startswith("TRAINER_BATTLE_"):
                acc["trainers"].append(args[0])
                roles = _trainer_arg_roles(cmd)
                for role, a in zip(roles, args[1:]):
                    if a in text_by_label:
                        trainer_texts.append((args[0], role, a, s["script_id"]))
            if cmd.startswith("warp") and args and args[0].startswith("MAP_"):
                acc["warps"].append(args[0])
            if cmd in ("special", "specialvar") and args:
                acc["specials"].append(args[-1])
            if cmd in ("playbgm", "savebgm", "fadenewbgm") and args:
                acc["music"].append(args[0])
            if cmd in ("pokemart", "pokemartdecoration", "pokemartdecoration2") and args:
                acc["marts"].append(args[0])
            if cmd == "register_matchcall" and args:
                acc["trainers"].append(args[0])
        for k, v in acc.items():
            s[k] = "|".join(dict.fromkeys(v))
        s["command_list"] = "|".join(dict.fromkeys(c for c, _ in s["_cmds"]))
    for s in scripts:
        for t in s.get("texts", "").split("|"):
            if t:
                text_by_label[t].setdefault("_users", []).append(s["script_id"])
    for t in texts:
        t["used_by_scripts"] = "|".join(t.pop("_users", []))

    # ---- marts -------------------------------------------------------------------------
    mart_rows = []
    labels_all = {}
    for rel_path, map_const in script_files():
        for b in parse_file(rel_path):
            labels_all[b["label"]] = (b, rel_path, map_const)
    for s in scripts:
        for mart in s.get("marts", "").split("|"):
            if mart and mart in labels_all:
                b, rp, mc = labels_all[mart]
                items = re.findall(r"\b(ITEM_\w+|DECOR_\w+)\b", " ".join(l for _, l in b["lines"]))
                for order, it in enumerate([i for i in items if i not in ("ITEM_NONE", "DECOR_NONE")], 1):
                    mart_rows.append({"mart_id": mart, "map_id": map_id(mc) if mc else s["map_id"], "order": order,
                                      "item_id": iid(it) if it.startswith("ITEM_") else "decoration:" + slug(it, "DECOR_"),
                                      "script_id": s["script_id"]})
    mart_rows = list({(r["mart_id"], r["order"]): r for r in mart_rows}.values())

    # ---- attribute dialogue to speakers (NPCs, signs, triggers) -----------------------
    events = read_csv(DATABASE_DIR / "map_events.csv") if False else None  # maps extractor runs in-process instead
    from extract_maps import extract as extract_maps_data
    map_data = extract_maps_data()
    npc_trainer = {}
    for ev in map_data["map_events"]:
        root = ev.get("script", "")
        if not root or root not in script_by_label:
            continue
        speaker = ev["object_id"]
        seen, order = set(), 0
        queue = deque([(root, 0)])
        while queue:
            lab, depth = queue.popleft()
            if lab in seen or depth > 8:
                continue
            seen.add(lab)
            s = script_by_label.get(lab)
            if not s:
                continue
            shared = not s["map_id"] and depth > 0
            for t in [x for x in s.get("texts", "").split("|") if x]:
                order += 1
                dialogue.append({"line_id": f"{speaker}#{order}", "speaker_entity_id": speaker, "map_id": ev["map_id"],
                                 "event_kind": ev["event_kind"], "order": order, "text_id": t,
                                 "role": _role_for(t, trainer_texts), "via_script": lab, "shared_script": "true" if shared else "false",
                                 "speaker_label": text_by_label[t]["speaker_label"], "text": text_by_label[t]["text"]})
            for tr in [x for x in s.get("trainers", "").split("|") if x]:
                if ev["event_kind"] == "object" and tr.startswith("TRAINER_"):
                    npc_trainer.setdefault(speaker, tr)
            if not shared or depth < 2:
                for j in [x for x in s.get("jumps", "").split("|") if x]:
                    queue.append((j, depth + 1))

    for npc, tr in npc_trainer.items():
        rels.append(rel(npc, "is_trainer", trid(tr)))
    for s in scripts:
        for tr in [x for x in s.get("trainers", "").split("|") if x.startswith("TRAINER_")]:
            if s["map_id"]:
                rels.append(rel(trid(tr), "battled_on", s["map_id"]))
        for it in [x for x in (s.get("items_gives", "")).split("|") if x.startswith("ITEM_")]:
            if s["map_id"]:
                rels.append(rel(s["map_id"], "gives_item", iid(it)))
        for sp in [x for x in s.get("species_gives", "").split("|") if x]:
            if s["map_id"]:
                rels.append(rel(s["map_id"], "gives_pokemon", sid(sp)))
        for sp in [x for x in s.get("species_battles", "").split("|") if x]:
            if s["map_id"]:
                rels.append(rel(sid(sp), "static_encounter_on", s["map_id"]))
    trainer_dialogue = [{"trainer_id": trid(tr), "role": role, "text_id": t, "script_id": sc,
                         "text": text_by_label[t]["text"]} for tr, role, t, sc in trainer_texts]

    # ---- flags & vars -----------------------------------------------------------------------
    for rel_path, kind, prefix in (("include/constants/flags.h", "flag", "FLAG_"), ("include/constants/vars.h", "var", "VAR_")):
        raw = read(rel_path)
        for m in re.finditer(r"^#define\s+(" + prefix + r"\w+)\s+((?:(?!//).)+?)\s*(?://\s*(.*))?$", raw, re.M):
            name, val, comment = m.group(1), m.group(2), (m.group(3) or "").strip()
            use = (flag_use if kind == "flag" else var_use).get(name, {})
            setters = sorted(use.get("set", set()) | use.get("clear", set()))
            checkers = sorted(use.get("check", set()))
            flags_rows.append({"flag_id": f"{kind}:{slug(name, prefix)}", "constant": name, "kind": kind, "value": val,
                               "comment": comment, "category": _flag_category(name),
                               "set_by_scripts": "|".join(setters), "checked_by_scripts": "|".join(checkers),
                               "maps": "|".join(sorted({script_by_label[x]["map_id"] for x in setters + checkers if x in script_by_label and script_by_label[x]["map_id"]})),
                               "unused": "true" if "UNUSED" in name else "false"})

    # NPC descriptions: first meaningful line of dialogue
    first_line = {}
    for d in dialogue:
        first_line.setdefault(d["speaker_entity_id"], d["text"])
    for ent in map_data["entities"]:
        if ent["entity_type"] == "npc" and ent["id"] in first_line:
            entities.append({"id": ent["id"], "description": first_line[ent["id"]][:400]})

    for s in scripts:
        s.pop("_cmds", None)
    return {"texts": texts, "scripts": scripts, "dialogue": dialogue, "trainer_dialogue": trainer_dialogue,
            "story_flags": flags_rows, "mart_inventory": mart_rows, "relationships": rels, "entities": entities}


def _split_cmd(line: str) -> tuple[str, list[str]]:
    parts = line.split(None, 1)
    if not parts:
        return "", []
    cmd = parts[0]
    args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
    return cmd, args


def _trainer_arg_roles(cmd: str) -> list[str]:
    if cmd in ("trainerbattle_single", "trainerbattle_rematch"):
        return ["intro", "defeat", "post_battle_script"]
    if cmd in ("trainerbattle_double", "trainerbattle_rematch_double"):
        return ["intro", "defeat", "not_enough_pokemon", "post_battle_script"]
    if cmd == "trainerbattle_no_intro":
        return ["defeat"]
    if cmd == "trainerbattle_two_trainers":
        return ["intro", "defeat", "_", "intro_b", "defeat_b"]
    return ["intro", "defeat"]


def _role_for(text_id: str, trainer_texts) -> str:
    for _, role, t, _ in trainer_texts:
        if t == text_id:
            return "trainer_" + role
    low = text_id.lower()
    for key in ("rematch", "postbattle", "intro", "defeat", "sign"):
        if key in low:
            return key
    return "dialogue"


def _flag_category(name: str) -> str:
    for prefix, cat in (("FLAG_HIDE_", "object_visibility"), ("FLAG_HIDDEN_ITEM", "hidden_item"), ("FLAG_ITEM_", "item_ball"),
                        ("FLAG_RECEIVED_", "received_reward"), ("FLAG_BADGE", "badge"), ("FLAG_DEFEATED_", "defeated"),
                        ("FLAG_VISITED_", "visited"), ("FLAG_TRAINER_", "trainer"), ("FLAG_DECORATION_", "decoration"),
                        ("FLAG_UNUSED", "unused"), ("FLAG_SYS_", "system"), ("FLAG_TEMP_", "temp"), ("FLAG_DAILY_", "daily"),
                        ("FLAG_ENABLE_", "enable"), ("FLAG_MET_", "met"), ("FLAG_CAUGHT_", "caught"), ("VAR_TEMP_", "temp"),
                        ("VAR_OBJ_GFX", "object_gfx"), ("VAR_UNUSED", "unused"), ("VAR_", "story_var")):
        if name.startswith(prefix):
            return cat
    return "story_event"


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
    print([x for x in d["dialogue"] if x["speaker_entity_id"] == "npc:littleroot-town:1"])
    print([x for x in d["scripts"] if x["script_id"] == "LittlerootTown_EventScript_Twin"])
    print([x for x in d["story_flags"] if x["constant"] == "FLAG_BADGE01_GET"])
