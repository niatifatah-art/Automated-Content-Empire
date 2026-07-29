# Installation

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg libsndfile1 espeak-ng

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

ace init
ace check
```

Optional voice engines:

```bash
python -m pip install -e ".[voice]"
python -m pip install -e ".[pocket-tts]"
```

For local text generation, install Ollama and pull at least one model. ACE's `auto` aliases prefer a suitable installed model rather than assuming one exact tag.

```bash
ollama list
ace models installed
ace models recommend
```

Portable testing or backup:

```bash
ace --home ~/PortableACE init
ACE_HOME=~/PortableACE ace check
```

## Safe upgrade from 0.3.x

```bash
cp -a ~/.config/ace ~/.config/ace.backup-before-v17
cp -a ~/.local/share/ace ~/.local/share/ace.backup-before-v17
ace init --upgrade
ace account show
ace check
```

The upgrader preserves accounts, secrets, routes, and user settings while backing up and refreshing the editable shipped catalogs and prompts.
