# Live API on the CIAT server (Jenkins)

The static API on GitHub Pages stays as it is. On top of it, the same FastAPI app runs live on a
CIAT server, deployed by Jenkins. Both serve the same contract (`docs/openapi.json`).

| | |
|---|---|
| Folder | `/opt/mosaic-api` (a clone of this repository, branch `main`) |
| Port | `4201` (`http://<server>:4201/`, docs at `/docs`, health at `/health`) |
| Python | miniforge environment `mosaic-api`, Python 3.14 |
| Configuration | [config/mosaic-api.server.yaml](../config/mosaic-api.server.yaml) |
| Data | `state/snapshot.json` (harvested resources); logs in `logs/api.log` and `logs/harvest.log` |
| Pipeline | [Jenkinsfile](../Jenkinsfile), which runs [deploy/server.sh](../deploy/server.sh) over SSH |
| Dependencies | pinned in [deploy/requirements-server.txt](../deploy/requirements-server.txt) |

## How it works

The server reads everything over https from what is already published:

- the MOSAIC catalogue build (standard, records, landscape profiles) at `https://mosaic-mfl.github.io/catalog`;
- the CDH catalogue on GitHub.

It does not clone or build the catalogue.

Each Jenkins run:

1. **Updates the code.** It fast-forwards `/opt/mosaic-api` to `origin/main`; the first time, it clones the repository. It never deploys over local changes.
2. **Installs.** It installs the pinned dependencies and the package into the environment (`server.sh install`).
3. **Harvests** (`server.sh harvest`). The snapshot is incremental, so only changed records are translated again. A source that fails keeps its previous records: the build turns **unstable** (yellow) and the API is still restarted. If every source fails, the API keeps the previous snapshot.
4. **Restarts the API** and waits up to 30 s for `/health` (`server.sh restart`). If it does not answer, the build fails and shows the end of `logs/api.log`.

The API reads the snapshot when it starts, which is why every run restarts it. The restart takes a few seconds.

**When it runs:**

- after a push to `main` (`pollSCM`, within 15 minutes);
- once a day (`cron`), which picks up CDH changes and catalogue merges;
- by hand (**Build Now**).

## Set up once

**On the server** (as the deploy user):

- Make sure `/opt/mosaic-api` exists and belongs to the deploy user. It should be empty, or already be a clone of this repository.
- The miniforge environment `mosaic-api` exists with Python 3.14 and pip.
  - `deploy/server.sh` looks for `conda.sh` in `/opt/miniforge3`, `/opt/conda`, `~/miniforge3` and `~/miniconda3`.
  - If miniforge is somewhere else, add `CONDA_SH=<miniforge>/etc/profile.d/conda.sh` to `SERVER_ENV` in the Jenkinsfile.
- Outbound https to `mosaic-mfl.github.io`, `github.com`, `codeload.github.com` and `raw.githubusercontent.com`. If the server goes out through a proxy, set `HTTPS_PROXY` for the deploy user; the API honours it.
- Port 4201 is open to whoever must reach the API (the website calls it from the browser).
- Optional: `fuser` (package `psmisc`), used to free the port if something else holds it.

**In Jenkins:**

1. Add two credentials:
   - `mosaic_api_host`: **Secret text**, the server's host name or IP;
   - `mosaic_api_deploy`: **SSH Username with private key**: the SSH user that owns `/opt/mosaic-api` and its private key, with a passphrase if the key has one. The matching public key goes in that user's `~/.ssh/authorized_keys` on the server.
   If they already exist under other ids, change the ids in the Jenkinsfile.
2. Create a **Pipeline** job with "Pipeline script from SCM":
   - Git: `https://github.com/MOSAIC-mfl/mosaic-api.git`
   - branch `*/main`
   - script path `Jenkinsfile`
   The job needs the **SSH Pipeline Steps** plugin (`sshCommand`).
3. Run it once with **Build Now**. The first run clones the repository and harvests every record, which takes about a minute.

## On the server by hand

Run from `/opt/mosaic-api`:

```sh
bash deploy/server.sh status     # running? what /health answers
bash deploy/server.sh harvest    # harvest now (the running API sees it after a restart)
bash deploy/server.sh restart
bash deploy/server.sh stop
tail -f logs/api.log
```

The defaults (`MOSAIC_API_HOME=/opt/mosaic-api`, `MOSAIC_API_PORT=4201`, `CONDA_ENV=mosaic-api`) can be changed with these environment variables. The header of `deploy/server.sh` lists them all.

## Website

Once the API answers at its final address, the website can read it live instead of the static files. That address should be https, behind CIAT's reverse proxy with a domain name; a page served over https cannot call an `http://` API.

- **Website:** this is the website's data-layer setting (live API URL), changed in the website repository.
- **CORS:** the origins allowed to call the API are in `http.cors_origins` of the server configuration.

## Updating dependencies

`deploy/requirements-server.txt` pins every package for Python 3.14 on Linux. After changing `pyproject.toml`, regenerate the file with the command in its header, run the tests on Python 3.14 and merge. The next deploy installs the new versions.
