# Make Your Trip Video

## Start

Open Docker Desktop, then run this from the repository root:

```bash
./scripts/start-local.sh
```

The first run installs or downloads the local vision model and can take several
minutes. The script opens Chrome at `http://localhost:3001/` and prints a bearer
token. Enter that token in Setup. It stays only in the ignored local `.env` file.

## Create From Files On This Mac

1. Enter a project name and click **New**.
2. Choose your trip photos and videos, then click **Upload**.
3. Click **Analyze** and wait for both plans.
4. Open **Review media** under each format. Include or exclude items, pin must-keep
   moments, use the arrow buttons to order clips, and adjust video start/seconds.
5. Click **Save review**, then **Approve** for both YouTube 16:9 and Shorts 9:16.
6. Click **Render**. Wait until the project says **ready**.
7. Under Outputs, click **Load**, then **Preview**. Use **Download MP4** beneath
   the preview to keep the final video wherever you choose on this Mac.

Your originals are not modified. Analysis and rendering run locally. Media,
thumbnails, generated videos, model weights and `.env` are excluded from Git.

## Create From Google Photos

Google Photos requires a one-time Google OAuth client. Follow the Google Photos
section in [LOCAL_TRIP_DEMO.md](LOCAL_TRIP_DEMO.md), restart with
`./scripts/start-local.sh`, then use **Status**, consent, **Connect Google Photos**,
**Choose album media**, and **Import locally**. Continue at Analyze above.

An album URL alone cannot authorize private media. Until OAuth is configured,
download the album to this Mac and use the file workflow; it is fully functional.

## Stop

```bash
./scripts/stop-local.sh
```

Stopping does not delete projects, source media, or outputs. Docker Desktop owns
the private local volume. Do not run `docker compose down -v` unless you intend to
delete that local data.
