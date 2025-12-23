This is a file to keep track of any assumptions I make in my project and things noticed in the original garmin-grafana repo

It doesn't appear like there is a local time zone coming from the original repo, to create the local time zone. In the .addon.yml I am binding the system timezone and making sure this is passed to my container however this is using linux specific commands it isn't clear if this carries over to windows may work on mac. This could definetly be a problem especially if the user is changing timezones relative to the machine running this program.

This is potentially an improvement to garmin-grafana might be to create a database entry for timezone changes or local timezone, ran into this issue when exporting my data with stamps. But likely going to be a problem for other add ons for this library too. See.yml how we overcame this however I think the fix only works in linux

Assuming also with the export that you want to take everything from your influx database (may need to revisit this to add more control for user especially if the influx database is very large) Could cause failure when creating the intraday structures.

Also, another item I am thinking for garmin-grafana may be to turn off the always polling feature. We figured out how to turn this on and off with the containers using the following command: 
docker compose stop garmin-fetch-data


