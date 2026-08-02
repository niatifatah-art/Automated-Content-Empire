# Migrating from ACE v1.7

## Back up persistent state

```bash
cp -a ~/.config/ace ~/.config/ace.backup-before-v2
cp -a ~/.local/share/ace ~/.local/share/ace.backup-before-v2
cp -a ~/.cache/ace ~/.cache/ace.backup-before-v2 2>/dev/null || true
```

## Install v2 into the current environment

```bash
source /path/to/ace/.venv/bin/activate
cd Automated-Content-Empire-2.1.0
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[voice]"
ace init --upgrade
```

## Rename or duplicate the Gemini secret

The old variable remains supported:

```dotenv
GEMINI_API_KEY=existing_key
```

The preferred v2 arrangement is:

```dotenv
GEMINI_API_KEY_PRIMARY=existing_key
GEMINI_API_KEY_BACKUP=second_authorized_key
```

Do not delete the old key until `ace credentials test` succeeds with the new configuration.

## Confirm the account

```bash
ace account show
ace account edit
ace account check
```

Add or review the new `editing` and `identity.humor` sections using `examples/account.yaml` as a reference.

## Validate the installation

```bash
ace --version
ace secrets status
ace credentials status
ace check --offline
ace test full --report
```

Then rerender an existing generation or create a new one. v1.7 generation folders are not modified until a v2 command writes a new caption/visual/edit plan.
