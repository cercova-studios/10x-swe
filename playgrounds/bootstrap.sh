#!/bin/bash
set -euo pipefail
cd /opt/10x-swe
python3 - <<'PY'
import hashlib, json, pathlib, platform, subprocess, tarfile, urllib.request
config = json.loads(pathlib.Path('playgrounds/runtime.json').read_text())
system = {'aarch64': 'aarch64-linux', 'x86_64': 'x86_64-linux'}[platform.machine()]
version = config['nix_version']
archive = pathlib.Path('/tmp/tenx-nix.tar.xz')
url = f'https://releases.nixos.org/nix/nix-{version}/nix-{version}-{system}.tar.xz'
urllib.request.urlretrieve(url, archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == config['nix_archives'][system], 'Nix checksum mismatch'
destination = pathlib.Path('/tmp/tenx-nix-install')
# The hash-verified upstream archive intentionally contains /nix/store symlinks.
with tarfile.open(archive) as bundle:
    bundle.extractall(destination, filter='fully_trusted')
subprocess.run(['sudo', 'mkdir', '/nix'], check=True)
subprocess.run(['sudo', 'chown', 'agent:agent', '/nix'], check=True)
subprocess.run([str(destination / f'nix-{version}-{system}/install'), '--no-daemon',
                '--no-channel-add', '--no-modify-profile'], check=True)
archive.unlink()
PY
export PATH="$HOME/.nix-profile/bin:$PATH"
# The microVM is the isolation boundary; this single-user Nix only supplies tools.
export NIX_CONFIG='experimental-features = nix-command flakes
sandbox = false
build-users-group =
max-jobs = 2'
nix build --no-write-lock-file ./playgrounds#default --out-link /home/agent/tenx-profile
export PATH="/home/agent/tenx-profile/bin:$PATH"
export PKG_CONFIG_PATH=/home/agent/tenx-profile/lib/pkgconfig
export CARGO_BUILD_JOBS=2
./knowledge setup --prefix /home/agent/knowledge
# Compilers remain available; completed setup retries use the installation receipt.
rm -rf /home/agent/knowledge/build /home/agent/.cargo/registry /home/agent/.cache/pip
cat > /home/agent/playground-env.sh <<'ENV'
export PATH="/home/agent/knowledge/bin:/home/agent/tenx-profile/bin:/home/agent/.nix-profile/bin:/usr/local/bin:/usr/bin:/bin"
export AGENT_KNOWLEDGE_HOME=/home/agent/knowledge
export SOURCE_INSIGHTS_INDEX_MODE=keyword
export PKG_CONFIG_PATH=/home/agent/tenx-profile/lib/pkgconfig
export DAGU_HOME=/home/agent/workflow-state/dagu
export CARGO_BUILD_JOBS=2
ENV
mkdir -p /home/agent/workspace /home/agent/workflow-state
rm -rf /tmp/tenx-nix-install
printf 'ready\n' > /home/agent/.playground-ready
