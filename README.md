# Garmin-Sleep-Check-Ins Overview
This is an add on to the the garmin-grafana prject created by @arpanghosh8453 that provides sleep insight messages to you from your locally hosted database.

This utlizes the existing Influx database as part of the garmin-grafana project

It reads from the database looking for new sleep files after they are downloaded from your garmin account.

When it find one, it generates either a text or image based summary based on that day's sleep data and comparing it to the past. 

It then messages you through Telegram with the summary and you why the sleep was that way.

When you reply, it stores your info back into the influx database as a sleepJournal measure and acknowledges it has been saved.

To see a demo of this on generic sleep data and the insight it would generate and the type of question it would ask you. Try out the demo.py. Note this is just for demo purposes it uses the command line not telegrm and your influx db will not be updated with your insight/response.

To export your data including your sleep journal entries in .csv files and .jsonl files use the sleep_data_export.py

If you want to get rid of all of your sleepJournal measures in the database use the delete_sleep_jounral_entries.py

##################
#QUICKSTART GUIDE:
##################
Make sure you have docker installed

Make sure you have the garmin-grafana repository installed and linked to your garmin account and there is data contained within it

You will need to have telegram insalled on the device you wish to communicate with this on i.e.) cellphone 
You need to setup a bot chat using botfather make note of the TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, see below section on details for setting this up.

Change the file name of the .env.example to just .env so that your docker container will know to use it and input the two telegram variable values so the program knows what chat to read and send messages to.

For now you can start up the program by running the rebuild.sh bash script from the terminal. Ensure you are in the Garmin-Sleep-Check-Ins folder and then run "bash rebuild.sh" there are two persistant containers one for polling the InfluxDatabase looking for new sleep data. And one to do longPolling of the telegram chat looking for new sleepJournal messages that need to be saved in the database.
 
To run one of the standalone python programs i.e.) demo.py, delete_sleep_journal_entries.py, sleep_data_export.py programs navigate into the Garmin-Sleep-Chek-Ins folder and use the below command currently written for demo.py but easily changed to any of the other one-shot scripts:
docker compose -f compose.addon.yml run --rm --build sleep-checkins python /app/src/demo.py

#########################
#Setting up Telegram Bot:
#########################
Download telegram 

In the search look for BotFather make sure you choose the one with the checkmark

message "/start"

message "/newbot"

message a name for the bot this is what is going to show up as the name on the chat

message a username this needs to be unique and you won't really need it for anything

Once created read the message it will tell you the TELEGRAM_BOT_TOKEN

Send the bot a message any message.

Then in a web browswer navigate to putting in your bot token from the previous step:
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates

Please note the JSON message won't appear if you are already running the telegram-listener service so you will need to stop the container

