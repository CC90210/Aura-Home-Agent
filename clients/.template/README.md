# Client Configuration Template

This directory is the starting point for every new AURA client deployment.

## How to Use This Template

**Step 1:** Copy this entire directory to a new directory named after the client.

```bash
cp -r clients/.template/ clients/{client_name}/
```

Use a consistent naming convention — lowercase, no spaces, use underscores:

```
clients/john_smith/
clients/oasis_hq/
clients/jane_doe_downtown/
```

**Step 2:** Edit `config_overrides.yaml` in the new directory.

Fill in all values specific to this client:
- Their name and city
- Their package tier (lite, standard, or pro)
- The Pi's hostname or IP address on their network
- Their room names and the entity IDs HA assigned to each device
- Which scenes and clap patterns are enabled for their package

The entity IDs must match exactly what Home Assistant shows. Find them at Settings → Devices & Services → Entities in the client's HA instance.

**Step 3:** Add a client-specific `.env` file.

```bash
cp .env.example clients/{client_name}/.env
```

Fill in the client's Pi network info, their HA long-lived access token, and their API keys (Govee, Spotify, etc.). This file must never be committed to git — it is listed in `.gitignore`.

**Step 4:** Run the client deployment script.

```bash
./scripts/deploy/deploy_client.sh {client_name}
```

This merges the client overrides with the base configuration and pushes everything to their Pi.

## What Lives Here vs in the Base Config

- **Base config** (`home-assistant/`): Universal automations and scenes that work for any installation. Never modify these for a specific client.
- **Client overrides** (`clients/{client_name}/`): Entity IDs, room names, enabled features, and any scenes that are unique to this client. All client-specific changes go here.

This separation means base config improvements can be deployed to all clients without overwriting their customizations.
