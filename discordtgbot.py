import discord
import asyncio
import requests
import mysql.connector
import time
from datetime import datetime

client = discord.Client()

db_pass = open("dbpass.cfg", "r").read()

# Variables to work with
members_old = ""
bot_restarted = True
last_announce = ""
offset = "-0"
logs = []
last_log = 0
chat_list = []
chat_list_user_names = []

# Get the Database running
db = mysql.connector.connect(host='192.168.2.67',
                             database='discordtgbot',
                             user='guru',
                             password=db_pass)
cursor = db.cursor()

# Get configs from database
sqlquery = "select * from configs"
cursor.execute(sqlquery)
records = cursor.fetchall()
discord_token = records[0][1]
tgbot_token = records[1][1]

####################
# Database methods #
####################

# Get the users with enabled notifications
def get_enabled_users():
    sqlquery = "select * from users where enabled = 'True'"
    cursor.execute(sqlquery)
    records = cursor.fetchall()
    for row in records:
        chat_list.append(row[1])
        chat_list_user_names.append(row[2])
    print("Getting messaged: " + str(chat_list_user_names))
    return chat_list

def get_username(telegram_id_func):
    try:
        sqlquery = "select user_name from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        return records[0]
    except:
        return telegram_id_func


####################
# Telegram methods #
####################

# Get updates from bot
def get_messages(offset_func):
    try:
        offset_url = "https://api.telegram.org/bot" + str(tgbot_token) + "/getUpdates?offset=" + offset_func
        bot_messages = requests.get(offset_url)
        return bot_messages.json()
    except:
        return False

# Send message to a chat
def send_message(chat, message_func, force):
    # Supress if Monday - Friday and not between 18 and 23
    print("it is day " + str(checktime("day")) + " and hour " + str(checktime("hour")))
    if checktime("day") < 4 and (checktime("hour") < 18 or checktime("hour") > 22) and not force:
        message = "Supressed message for {} due to Day or Time".format(get_username(chat))
        log(message)
        return "suppressed"
    else:
        try:
            message = "Send message to {}: {}".format(get_username(chat), message_func)
            log(message)
            requests.get("https://api.telegram.org/bot" + str(tgbot_token) + "/sendMessage?chat_id=" + str(chat) + "&text=" + str(message_func))
            return message_func
        except:
            return False

###################
# Discord methods #
###################

def get_online_status(channel):
    voice_channel = client.get_channel(channel)
    members = voice_channel.members
    member_list = []
    for member in members:
        member_list.append(member.name)
    if member_list:
        message = "Online right now: {}".format(member_list)
        return message
    else:
        message = "Nobody is online, you are on your own! Are you are lonely?"
        return message


################
# Misc methods #
################

# Log to console
def log(output):
    global last_log

    # Print new Timestamp in log if last log is older than 5 seconds
    if time.time() - last_log > 5:
        print("\n-------------------\n" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n-------------------\n" + str(output))
        last_log = time.time()
    else:
        print(str(output))
        last_log = time.time()

    # Write into Database
    sqlquery = "INSERT INTO messages (message_text) VALUES (\"{}\")".format(output)
    cursor.execute(sqlquery)
    db.commit()

# Check hour as of right now
def checktime(asked):
    if asked == "hour":
        format = "%H"
        today = datetime.today()
        hour = today.strftime(format)
        return int(hour)
    if asked == "day":
        day = datetime.today().weekday()
        return int(day)


############
# Main Bot #
############

# Log bot restart
log("The bot restarted!")

async def telegram_bridge():
    global offset
    global chat_list
    global chat_list_user_names
    global members_old
    global bot_restarted
    global last_announce

    await client.wait_until_ready()
    while not client.is_closed():
        try:
            # Variables for the bot
            channel_id = 633023114095231027
            voice_channel = client.get_channel(channel_id)
            members = voice_channel.members
            member_list = []

            # Check if someone joined or left
            if members != members_old:
                # Put them into a list
                for member in members:
                    member_list.append(member.name)

                # Verbose for cli
                print("Now online: " + str(member_list))

                # Check if the new member list is longer (char wise due to laziness)
                # We only want to announce ppl that come into the channel
                # Not if they leave
                if len(member_list) > len(members_old):
                    message = "Im Discord: " + str(member_list)
                    # Only announce to chat if the bot did not restart
                    if not bot_restarted:
                        # Only announce if the list is altered from the last time posted to the chat
                        if len(last_announce) != len(message):
                            for chat in get_enabled_users():
                                last_announce = send_message(chat, message, False)

                # Check if the last one left the channel
                elif not member_list and last_announce != "suppressed":
                    message = "Discord: Der letzte ist gegangen!"
                    # Only announce to chat if the bot did not restart
                    if not bot_restarted:
                        # Send message to the chat and remember
                        for chat in get_enabled_users():
                            last_announce = send_message(chat, message, False)

            # Update the variables for next loop
            members_old = members
            if bot_restarted:
                last_announce = "Im Discord: " + str(member_list)
                bot_restarted = False

            ###################
            # Chat monitoring #
            ###################

            # Get updates from Telegram
            bot_messages_json = get_messages(offset)

            # Check the amount of messages received
            try:
                message_amount = len(bot_messages_json["result"])
            except KeyError and TypeError:
                message_amount = 0

            # Check messages if exists
            if message_amount != 0:
                # Suppress old actions if bot restarted
                if bot_restarted:
                    bot_restarted = False
                else:
                    # Go through all new messages
                    message_counter = 0
                    for texts in bot_messages_json["result"]:
                        # Catch key error due to other updates than message
                        try:
                            bot_messages_text_single = str(
                                bot_messages_json["result"][message_counter]["message"]["text"])
                            log("New Message: " + bot_messages_text_single)

                            # Check who wrote the message
                            check_user = str(bot_messages_json["result"][message_counter]["message"]["from"]["id"])
                            check_user_name = str(bot_messages_json["result"][message_counter]["message"]["from"]["username"])
                            log("From user: " + get_username(check_user))

                            if get_username(check_user) == check_user:
                                # Insert new user to database
                                sqlquery = "INSERT INTO users (telegram_id, user_name) VALUES (\"{}\",\"{}\")".format(check_user, check_user_name)
                                cursor.execute(sqlquery)
                                db.commit()
                                log("Created new User")
                                # Welcome the new User
                                message = "Hello {}, seems you are new here. Welcome!\nYou can use the commands /enable or /disable and /who_is_online - Just try!".format(check_user_name)
                                send_message(check_user, message, True)

                            # Check for commands
                            # Split message by " " to be able to parse it easier
                            splitted = bot_messages_text_single.split(' ')

                            # The user wants to get messages
                            if splitted[0] == "/enable":
                                # Tell the user that he will get messages now
                                message = "You will now receive messages"
                                log(message)
                                send_message(check_user, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = 'True' WHERE telegram_id = " + str(check_user)
                                cursor.execute(sqlquery)
                                db.commit()

                            # The user does not want to get messages
                            if splitted[0] == "/disable":
                                # Tell the user that he will no longer get messages
                                message = "You will no longer receive messages"
                                log(message)
                                send_message(check_user, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = 'False' WHERE telegram_id = " + str(check_user)
                                cursor.execute(sqlquery)
                                db.commit()

                            # The user does not want to get messages
                            if splitted[0] == "/who_is_online":
                                # Tell the user who is online right now
                                message = get_online_status(channel_id)
                                log(message)
                                send_message(check_user, message, True)

                            # Update the message counter
                            message_counter = message_counter + 1

                        # Discard all other messages
                        except KeyError:
                            log("Another type of message received")

                # Set new offset to acknowledge messages on the telegram api
                offset = str(bot_messages_json["result"][message_amount - 1]["update_id"] + 1)

            # Reset variables
            chat_list = []
            chat_list_user_names = []

            # Sleep some seconds
            await asyncio.sleep(5)

        except Exception as e:
            print(str(e))

# Get the loop going
client.loop.create_task(telegram_bridge())

# Start the actual bot
client.run(discord_token)

if (db.is_connected()):
    db.close()
    cursor.close()
    print("MySQL connection is closed")
