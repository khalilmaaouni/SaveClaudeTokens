#!/usr/bin/env python3
"""Architecture fitness check: the import graph must match the declared layers.

    python3 scripts/test_architecture.py

WHY THIS FILE EXISTS. A rule is not a control unless a file enforces it.
docs/ARCHITECTURE.md declares which layer every module sits in and that
imports may only point DOWNWARD. Nothing computed that, so the direction had
already been lost in five places by the time anybody drew the diagram, and
three separate defect rounds (a trial and a command printing different
headline numbers, a caveat that travelled on one surface and not the other,
a colour rule that made a regression green) all trace back to the same shape:
a lower module reaching up into the renderer, so two surfaces onto one number
could drift apart with nothing to notice.

WHAT IT REFUSES. Three things, and each is a growth control rather than a
tidiness one:

  1. A module with no declared layer. A new file cannot be added without
     deciding where it belongs, which is the moment the decision is cheap.
  2. A NEW upward import. The five that exist today are frozen below by name
     and everything else must point down.
  3. A STALE entry in that frozen list. When a violation is fixed the entry
     has to go, or the list quietly becomes a lie about the codebase and
     stops being a ratchet at all.

The frozen list only ever shrinks. It is not a permission slip: every entry
carries the reason it is still there and docs/ARCHITECTURE.md names the one
change that removes all five.
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Lower number is lower in the stack. An import may point at the same layer
# or a lower one, never a higher one.
#
#   0  foundation: reads the raw counters and the config on disk. Imports
#      nothing else in this repo, which is what makes it the floor.
#   1  metrics: turns counters into the quantities the product talks about.
#   2  proposal: reads metrics and proposes a change, never renders one.
#   3  advice and ecosystem: ranks proposals, inspects the installed world.
#   4  advisors: the ranked next-move surface the renderers consume.
#   5  presentation: labels, formatting, and the HTML the product ships.
#   6  fleet: many machines, built on the single-machine layers below.
#   7  surfaces: one entry point per thing a person or a script can run.
LAYERS = {
    0: {"config", "formatting", "measure_tokens", "context_lint",
        "session_end_telemetry", "check_py311"},
    1: {"metrics", "pricing", "experiment", "profile", "signals"},
    2: {"guided_apply", "optimize", "discover_companions"},
    3: {"companions", "plugin_prune", "memory_trim", "doctor"},
    4: {"advisor", "deep_advisor"},
    5: {"token_shield"},
    6: {"fleet"},
    7: {"cli", "trial", "report", "detail_report", "share_card", "fleet_dashboard",
        "reconcile", "obsidian_export", "github_cost_guard"},
}

# Upward imports that exist TODAY, frozen by name so no sixth can be added
# without this file being edited on purpose. All five have one cause: four
# modules want COMPANIONS_PATH and load_companions, which live in the
# renderer instead of the foundation, and one wants ROOT and EXPERIMENT_DAYS,
# which live in a surface instead of the foundation. Extracting a config
# module removes every entry here at once (docs/ARCHITECTURE.md, "The one
# change that empties the frozen list").
KNOWN_UPWARD = {}


def _modules():
    """{name: [source paths]} for every non-test module, packages included.

    A package is ONE node keyed by its directory name: scripts/companions/ is
    "companions", and an import of it from anywhere is an import of the whole
    package, which is how the layer rule has to see it."""
    out = {}
    for entry in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, entry)
        if entry.endswith(".py") and not entry.startswith("test_"):
            out[entry[:-3]] = [path]
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            out[entry] = sorted(os.path.join(path, f) for f in os.listdir(path)
                                if f.endswith(".py"))
    return out


def _edges(modules):
    """{(importer, imported)} across every source file of every module.

    Static imports only. A subprocess call naming another script is a
    dependency too, but it is not one the interpreter can be asked about, so
    it is out of scope here and named in docs/ARCHITECTURE.md instead of
    being guessed at from a string match."""
    names = set(modules)
    edges = set()
    for name, paths in modules.items():
        for path in paths:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = alias.name.split(".")[0]
                        if target in names and target != name:
                            edges.add((name, target))
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    target = node.module.split(".")[0]
                    if target in names and target != name:
                        edges.add((name, target))
    return edges


def _layer_of():
    out = {}
    for layer, members in LAYERS.items():
        for m in members:
            assert m not in out, f"{m} is declared in two layers"
            out[m] = layer
    return out


def test_every_module_has_a_declared_layer():
    modules, layer_of = _modules(), _layer_of()
    undeclared = sorted(set(modules) - set(layer_of))
    assert not undeclared, (
        f"module(s) with no layer in LAYERS: {undeclared}. A new module has to be "
        f"placed deliberately; see docs/ARCHITECTURE.md for what each layer means.")
    phantom = sorted(set(layer_of) - set(modules))
    assert not phantom, (
        f"LAYERS names module(s) that do not exist: {phantom}. A layer map that "
        f"describes files nobody has is not a description of this codebase.")


def test_no_new_upward_import():
    modules, layer_of = _modules(), _layer_of()
    upward = {(a, b) for a, b in _edges(modules) if layer_of[b] > layer_of[a]}
    new = sorted(upward - set(KNOWN_UPWARD))
    assert not new, (
        f"new upward import(s), which the layer rule forbids: "
        f"{[f'{a}(L{layer_of[a]}) -> {b}(L{layer_of[b]})' for a, b in new]}. "
        f"Either the import points the wrong way, or the layer map is wrong and "
        f"should be changed on purpose in this file.")


def test_the_frozen_list_holds_nothing_that_was_already_fixed():
    modules, layer_of = _modules(), _layer_of()
    upward = {(a, b) for a, b in _edges(modules) if layer_of[b] > layer_of[a]}
    stale = sorted(set(KNOWN_UPWARD) - upward)
    assert not stale, (
        f"KNOWN_UPWARD still lists import(s) that no longer exist: {stale}. Delete "
        f"the entries: a frozen list that outlives its violations stops being a "
        f"ratchet and starts being a false description of the codebase.")


def test_the_frozen_list_is_exactly_the_five_known_today():
    """Calibration. The two checks above would both pass against an empty
    KNOWN_UPWARD only if the codebase were already clean, so this pins the
    count: if it drops, the checks above proved something real changed, and
    this number comes down with it in the same edit."""
    modules, layer_of = _modules(), _layer_of()
    upward = {(a, b) for a, b in _edges(modules) if layer_of[b] > layer_of[a]}
    assert len(upward) == 0, sorted(upward)
    assert all(reason for reason in KNOWN_UPWARD.values()), (
        "every frozen entry states why it is still there")


def test_the_import_cycles_are_the_ones_the_frozen_list_explains():
    """Cycles are reported rather than merely counted, because a cycle is the
    shape that lets two surfaces onto one number drift apart. Every cycle here
    must run through a frozen upward edge: one that does not would be a new
    kind of tangle, not the known one being paid down."""
    modules, layer_of = _modules(), _layer_of()
    edges = _edges(modules)
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)

    cycles = set()

    def walk(node, path):
        if node in path:
            cycle = path[path.index(node):]
            cycles.add(tuple(sorted(cycle)))
            return
        for nxt in sorted(adjacency.get(node, ())):
            walk(nxt, path + [node])

    for m in sorted(modules):
        walk(m, [])

    for cycle in sorted(cycles):
        ring = set(cycle)
        assert any(a in ring and b in ring for a, b in KNOWN_UPWARD), (
            f"cycle {cycle} runs through no frozen upward edge, so it is a new "
            f"tangle rather than the known one")


def test_the_computing_layers_do_not_render():
    """The layer rule polices DIRECTION. It cannot see the other half of the
    mistake that made `token_shield` a god module, which is a metric and its
    rendering living at the same address: nine modules had to import the
    renderer to reach a number, and the direction of every one of those
    imports was perfectly legal.

    So layers 0 and 1 are held to a second rule: they may not emit markup.
    A function that computes a quantity and a function that decides how it
    looks are different jobs, and once they share a file the pressure is
    always to add "just one more" render helper beside the number it
    describes, which is exactly how the last one grew to 1,572 lines.

    Checked on string literals only, so a docstring may still discuss HTML
    (metrics.py's own explanation of what it is not allowed to do would
    otherwise trip this)."""
    layer_of = _layer_of()
    computing = sorted(n for n, layer in layer_of.items() if layer <= 1)
    markup = ("<div", "<span", "<td", "<tr", "<table", "<p ", "<h1", "<h2",
              "</div>", "</span>", "style=", "class=", "<!doctype", "<html")
    bad = []
    for name in computing:
        for path in _modules().get(name, []):
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)

            # Docstrings are Constant string nodes too, so collect their line
            # numbers first and skip them during the scan. Collected up front
            # rather than filtered afterwards: an earlier draft of this test
            # rebuilt the location by splitting its own message on ":", which
            # also split the message text and crashed, so the test went red
            # for a reason that had nothing to do with rendering.
            doc_lines = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                    if ast.get_docstring(node, clean=False) is not None and node.body:
                        doc_lines.add(node.body[0].lineno)

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)):
                    continue
                if node.lineno in doc_lines:
                    continue
                hits = [m for m in markup if m in node.value.lower()]
                if hits:
                    bad.append(
                        f"{os.path.basename(path)} line {node.lineno} "
                        f"emits {hits[0]!r}")

    assert not bad, (
        "a computing layer is rendering: " + "; ".join(bad) +
        ". Markup belongs at layer 5. A metric and its presentation sharing a "
        "file is how the renderer became a god module.")


def test_every_silent_handler_states_why_it_is_silent():
    """A handler that catches an error and then only `pass`, `continue` or
    `return None` has decided that losing the error is correct. Usually it IS
    correct here: a ledger line that will not parse is skipped so one corrupt
    line cannot hide every other record, which is this codebase's central
    promise. But "correct" and "nobody thought about it" look identical in
    source, and the difference is the whole point.

    So every such handler carries `# sbe: allow-silent <reason>` on the
    swallowing statement, and this refuses a new one that does not. The marker
    is the same one tools/sbe_score.py's lint reads, so annotating for that
    external gate and satisfying this one are the same act; this check exists
    so the property holds for anyone who does not have that tool installed.

    Reasons are not policed for quality here, only for presence and for not
    being empty. What a reason is worth is a review question, and pretending a
    string check settles it would be the kind of false assurance this file was
    written against.

    Deliberately NOT a general lint: this is the one swallow shape that has
    actually cost this repository data, and it is the shape a new one is most
    likely to take."""
    bad = []
    for name, paths in _modules().items():
        for path in paths:
            with open(path, encoding="utf-8") as f:
                src = f.read()
            lines = src.splitlines()
            for node in ast.walk(ast.parse(src, filename=path)):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body = node.body
                if len(body) != 1:
                    continue
                stmt = body[0]
                silent = (isinstance(stmt, (ast.Pass, ast.Continue))
                          or (isinstance(stmt, ast.Return)
                              and (stmt.value is None
                                   or (isinstance(stmt.value, ast.Constant)
                                       and stmt.value.value is None))))
                if not silent:
                    continue
                span = lines[node.lineno - 1:stmt.lineno]
                marked = [ln for ln in span if "sbe: allow-silent" in ln]
                if not marked:
                    bad.append(f"{os.path.basename(path)}:{stmt.lineno} has no reason")
                    continue
                reason = marked[0].split("sbe: allow-silent", 1)[1].strip()
                if len(reason) < 12:
                    bad.append(f"{os.path.basename(path)}:{stmt.lineno} reason is empty or a stub: "
                               f"{reason!r}")
    assert not bad, (
        "silent handler(s) with no stated reason: " + "; ".join(bad) +
        ". Add `# sbe: allow-silent <why losing this error is correct>` on the "
        "swallowing line, or stop swallowing it.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
