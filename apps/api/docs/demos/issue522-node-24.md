# #522 — Node 24 LTS for CI and the dev deploy

*2026-09-18T18:00:07Z*

AC1: every workflow reads the runtime from `.nvmrc`. No hardcoded `node-version` is left.

```bash
cat .nvmrc
echo "hardcoded node-version lines: $(grep -rhE '^\s*node-version:' .github/workflows/ | wc -l)"
echo "setup-node steps: $(grep -rho 'actions/setup-node@' .github/workflows/ | wc -l)   reading .nvmrc: $(grep -rho "node-version-file: '.nvmrc'" .github/workflows/ | wc -l)"
```

```output
24
hardcoded node-version lines: 0
setup-node steps: 8   reading .nvmrc: 8
```

AC3: `engines.node` and `@types/node` follow the `.nvmrc` major, and the lockfile resolves `@types/node` 24.x.

```bash
node -e '
const r=require("./package.json"), w=require("./apps/web/package.json"), l=require("./package-lock.json");
console.log("engines.node:      ", r.engines.node);
console.log("@types/node range: ", w.devDependencies["@types/node"]);
console.log("@types/node locked:", l.packages["node_modules/@types/node"].version);'
```

```output
engines.node:       >=24
@types/node range:  ^24
@types/node locked: 24.13.5
```

AC2 (local half): the deploy's own `USE_NODE` line, run through a real nvm. `PATH` starts with a Node 20 bin, standing in for the VPS's system node. The runner assigns the line, and a fresh `bash -c` runs it, the same way ssh hands it to the VPS.

```bash
F=$(mktemp -d); cp .nvmrc "$F/"
eval "$(grep -oP "^\s*\KUSE_NODE='[^']+'" .github/workflows/deploy-dev.yml)"
env -i HOME="$HOME" PATH="$HOME/.nvm/versions/node/v20.19.6/bin:/usr/bin:/bin" \
  bash -c "echo before: \$(node -v); cd $F || exit 1; $USE_NODE; echo npm would now run on: \$(node -v)"
echo "exit $?"; rm -rf "$F"
```

```output
before: v20.19.6
node -v: v24.21.0 (/home/frankbria/.nvm/versions/node/v24.21.0/bin/node)
npm would now run on: v24.21.0
exit 0
```

AC2 (failure path): if the node is the wrong major, or nvm is missing, the line exits 1 before npm runs. That fails the ssh call, which fails the deploy step. The pinned tests run exactly this path against a stub nvm:

```bash
python3 -m pytest deployment/tests/test_node_runtime.py -v -k prelude 2>&1 | grep -E "PASSED|FAILED|passed|failed"
```

```output
deployment/tests/test_node_runtime.py::test_prelude_runs_npm_on_the_nvmrc_major_and_logs_it PASSED [ 16%]
deployment/tests/test_node_runtime.py::test_prelude_fails_before_npm_on_a_mismatch[v20.19.0] PASSED [ 33%]
deployment/tests/test_node_runtime.py::test_prelude_fails_before_npm_on_a_mismatch[v240.0.0] PASSED [ 50%]
deployment/tests/test_node_runtime.py::test_prelude_fails_before_npm_on_a_mismatch[v2.0.0] PASSED [ 66%]
deployment/tests/test_node_runtime.py::test_prelude_fails_before_npm_without_nvm PASSED [ 83%]
deployment/tests/test_node_runtime.py::test_prelude_falls_back_to_an_installed_node_when_install_fails PASSED [100%]
======================= 6 passed, 7 deselected in 0.05s ========================
```

AC4: nothing in the deploy touches the shared system node. There is no symlink into /usr/local/bin, no `nvm alias default`, and no `.bashrc` edit. The node comes from the deploy user's nvm and is selected per command.

```bash
git diff main...HEAD -- .github/workflows/deploy-dev.yml | grep -E '^\+.*(/usr/local/bin|alias default|bashrc|ln -s)' || echo "no global runtime changes in the deploy diff"
```

```output
no global runtime changes in the deploy diff
```
