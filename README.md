# Garmin-Sleep-Check-Ins
This is an add on the the garmin-grafana prject created by @arpanghosh8453 that provides sleep insight messages to you from your locally hosted database.

This utlizes the existing Influx database as part of the garmin-grafana project

It reads from the database looking for new sleep files after uploaded to your garmin account.

When it find one, it generates insights based on the file and your previous sleep history. 

It then messages you (Likely through Telegram to start) with this insight and asks you questions 

When you reply, it stores your info back into the influx database as a sleep-insight (effectively acting like a sleep journal)

To see a demo of this on generic sleep data and the insight it would generate and the type of question it would ask you. Try out the demo.py. Note this is just for demo purposes your influx db will not be updated with your insight/response.

To run the program use the following command this does one-shot build of the docker container and runs the script that is currently uncommented (demo.py default) in the Dockerfile stored in the root of the repo:
docker compose -f compose.addon.yml run --rm --build \--user "$(id -u):$(id -g)" \sleep-checkins

In the future need to create a cleaner install with a bash script
