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
intraday_announced = False

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

# Get main discord channels from database
sqlquery = "select room_id from discord_channel where main = 'True'"
cursor.execute(sqlquery)
records = cursor.fetchone()
main_channel_id = int(records[0])

####################
# Database methods #
####################

# Get the users with enabled notifications
# Returns a list with telegram chat IDs
def get_enabled_users():
    sqlquery = "select * from users where enabled = 'True'"
    cursor.execute(sqlquery)
    records = cursor.fetchall()
    for row in records:
        chat_list.append(row[1])
        chat_list_user_names.append(row[2])
    log(2,"Enabled users: " + str(chat_list_user_names))
    return chat_list

# Checks if a given user wants to get the message that the last one left discord.
# Returns True or False
def get_setting_leave_messages(telegram_id_func):
    try:
        sqlquery = "select leave_messages from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        if records[0] == "False":
            return False
        else:
            return True
    except:
        return True

# Converts a given Telegram chat ID to the bot-username
# Returns the Username
def get_username(telegram_id_func):
    try:
        sqlquery = "select user_name from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        return records[0]
    except:
        return telegram_id_func

# Converts a given Telegram chat ID to the bot-username
# Returns the Discord-Username
def get_discord_username(telegram_id_func):
    try:
        sqlquery = "select discord_username from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        if records[0]:
            return records[0]
        else:
            return telegram_id_func
    except:
        return telegram_id_func

# Checks if a user wants to supress messages based on the current time
# Returns True or False
def get_supress_status(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select supress from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        # If User wants to supress check the time
        if records[0] == "True" and checktime("day") < 4 and (checktime("hour") < 18 or checktime("hour") > 22):
            # User wants to supress and its out of the notification time
            return True
        else:
            # User does not want to supress or its in the notification time
            return False
    except:
        # If it is not set we assume it should be supressed
        return True

# Checks if a user wants to supress messages in general
# Returns True or False
def get_supress_config(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select supress from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        # If User wants to supress check the time
        if records[0] == "True":
            # User wants to supress
            return True
        else:
            # User does not want to supress
            return False
    except:
        # If it is not set we assume it should be supressed
        return True

# Check the day_status of a given user
# Returns the day_status
def get_day_status(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select day_status from users where telegram_id = {} AND day_status_day = {}".format(telegram_id_func, checktime("day"))
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        # Return the day_status
        return records[0]
    except:
        # Return False if not set
        return False

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
    # Check if user wants to supress notifications on workdays
    if get_supress_status(chat) and not force:
        # Supress if Monday - Friday and not between 18 and 23
        message = "Supressed message for {} due to Day or Time".format(get_username(chat))
        log(1,message)

    # Supress since user does not come online today
    elif get_day_status(chat) == "/not_today" and not force:
        message = "Supressed message for {} due to day_status".format(get_username(chat))
        log(1,message)

    # Some messages like bot replies to the user need to be forced
    else:
        try:
            message = "Send message to {}: {}".format(get_username(chat), message_func)
            log(1,message)
            requests.get("https://api.telegram.org/bot" + str(tgbot_token) + "/sendMessage?chat_id=" + str(chat) + "&text=" + str(message_func))
            return message_func
        except:
            return False

###################
# Discord methods #
###################

# Checks who is online right now
# Also checks the day_status of the users
# Returns a message with optional day status
def get_online_status(channel, status):
    voice_channel = client.get_channel(channel)
    members = voice_channel.members
    member_list = []
    for member in members:
        member_list.append(member.name)
    if member_list:
        message = "Online right now: {}".format(member_list)
    else:
        message = "Nobody is online, you are on your own!"

    if status:
        for user in get_enabled_users():
            status = get_day_status(user)
            if status:
                message = message + "\n" + get_username(user) + "'s Status: " + status

    return message

# Checks if a given user is online
# Returns True or False
def is_user_in_channel(telegram_id_func, channel):
    if get_discord_username(telegram_id_func) in get_online_status(channel, False):
        return True
    else:
        return False

################
# Misc methods #
################

# Log to console
def log(verbosity, output):
    global last_log

    # Print new Timestamp in log if last log is older than 5 seconds
    if time.time() - last_log > 5:
        print("\n-------------------\n" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n-------------------\n" + str(output))
        last_log = time.time()
    else:
        print(str(output))
        last_log = time.time()

    # Write into Database
    sqlquery = "INSERT INTO messages (message_text, verbosity) VALUES (\"{}\", \"{}\")".format(output, verbosity)
    cursor.execute(sqlquery)
    db.commit()

# Looks up the current Day or Hour
# Hours: 0-23 or Days: 0-7 (Monday-Sunday)
# Returns the Hour or Day as integer
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
log(5, "The bot restarted!")

# Only needed if the bot did restart
if checktime("hour") > 17:
    intraday_announced = True

async def telegram_bridge():
    global offset
    global chat_list
    global chat_list_user_names
    global members_old
    global bot_restarted
    global last_announce
    global cursor
    global intraday_announced

    # Wait after restart till the bot is logged into discord
    await client.wait_until_ready()
    # Start the whole loop
    while not client.is_closed():
        try:
            # Check if we have a connection to the database or try to reconnect
            if not db.is_connected():
                cursor = db.cursor()
                log(5, "Reconnected to Database")

            # Variables for the bot
            voice_channel = client.get_channel(main_channel_id)
            members = voice_channel.members
            member_list = []

            # Announce if someone is online and it turns 18 o'clock
            # Announce only to user that supressed the messages before
            if members and not bot_restarted:
                if not intraday_announced:
                    if checktime("hour") == 18:
                        # Log Action
                        log(2,"Will announce online members to prior supressed users.")
                        # Put user into a list
                        for member in members:
                            member_list.append(member.name)
                        # Message users
                        for chat in get_enabled_users():
                            # Check that the user is not online
                            if is_user_in_channel(chat, main_channel_id) == False:
                                # User with supress enabled getting notified
                                if get_supress_config(chat):
                                    message = "Im Discord: {} \nMessage: /on_the_way  /later  /not_today".format(member_list)
                                    send_message(chat, message, False)
                                # User was not supressed
                                else:
                                    log(2,"{} was not supressed and does not need to be notified!".format(get_discord_username(chat)))
                            # User is online
                            else:
                                log(2,"{} is online and does not need to be notified!".format(get_discord_username(chat)))
                        intraday_announced = True

            # Check if someone joined or left
            if members != members_old:
                # Put them into a list
                for member in members:
                    member_list.append(member.name)

                # Verbose for cli
                log(2,"Now online: " + str(member_list))

                # Check if the new member list is longer (char wise due to laziness)
                # We only want to announce ppl that come into the channel
                # Not if they leave
                if len(member_list) > len(members_old):
                    # Only announce to chat if the bot did not restart
                    if not bot_restarted:
                        # Check who wants to get messages
                        for chat in get_enabled_users():
                            # Check if user is online
                            if is_user_in_channel(chat, main_channel_id) == False:
                                message = "Im Discord: {} \nMessage: /on_the_way  /later  /not_today".format(member_list)
                                send_message(chat, message, False)
                                last_announce = message
                            # If user is online he does not need to be notified
                            else:
                                log(2,"{} is online and does not need to be notified!".format(get_discord_username(chat)))

                # Check if the last one left the channel
                elif not member_list:
                    message = "Discord: Der letzte ist gegangen!"
                    # Only announce to chat if the bot did not restart
                    if not bot_restarted:
                        # Send message to the chat and remember
                        for chat in get_enabled_users():
                            if get_username(chat) not in last_announce and get_setting_leave_messages(chat) is True:
                                send_message(chat, message, False)
                                last_announce = "Empty"
                            else:
                                log(2,"The User was online right now or does not want to be notified!")

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
                            # Get the message
                            bot_messages_text_single = str(
                                bot_messages_json["result"][message_counter]["message"]["text"])
                            log(2,bot_messages_json)

                            # Check who wrote the message
                            check_user = str(bot_messages_json["result"][message_counter]["message"]["from"]["id"])
                            check_user_name = str(bot_messages_json["result"][message_counter]["message"]["from"]["first_name"])

                            # Log the message
                            log(1,"New Message from {}: {}".format(get_username(check_user), bot_messages_text_single))

                            # Create new user if unknown
                            if get_username(check_user) == check_user:
                                # Insert new user to database
                                sqlquery = "INSERT INTO users (telegram_id, user_name) VALUES (\"{}\",\"{}\")".format(check_user, check_user_name)
                                cursor.execute(sqlquery)
                                db.commit()
                                log(2,"Created new User")
                                # Welcome the new User
                                message = "Hello {}, seems you are new here. Welcome!\nYou can use the commands /enable " \
                                          "or /disable and /who_is_online - Just try!\n" \
                                          "You should set your Discord Username with [ /set_discord_username YOUR-USERNAME ]\n" \
                                          "You can also supress notifications on workdays between 18 and 23 o'clock with /toggle_workday_notifications\n" \
                                          "And if you dont want to get notifications if the last user left the Discord use " \
                                          "/toggle_leave_notifications".format(check_user_name)
                                send_message(check_user, message, True)

                            # Check for commands
                            # Split message by " " to be able to parse it easier
                            splitted = bot_messages_text_single.split(' ')

                            # The user wants to get messages
                            if splitted[0] == "/enable":
                                # Tell the user that he will get messages now
                                message = "You will now receive messages"
                                send_message(check_user, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = 'True' WHERE telegram_id = " + str(check_user)
                                cursor.execute(sqlquery)
                                db.commit()

                            # The user does not want to get messages
                            if splitted[0] == "/disable":
                                # Tell the user that he will no longer get messages
                                message = "You will no longer receive messages"
                                send_message(check_user, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = 'False' WHERE telegram_id = " + str(check_user)
                                cursor.execute(sqlquery)
                                db.commit()

                            # The user wants to now who is online
                            if splitted[0] == "/who_is_online":
                                # Tell the user who is online right now
                                message = get_online_status(main_channel_id, True)
                                send_message(check_user, message, True)

                            # The user wants to toggle workday notifications
                            if splitted[0] == "/toggle_workday_notifications":
                                # Toggle setting
                                if get_supress_status(check_user) == "True":
                                    message = "You will get notification all day long!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET supress = 'False' WHERE telegram_id = " + str(check_user)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                else:
                                    message = "You will get notification on weekends and on workdays between 18-23 o'clock!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET supress = 'True' WHERE telegram_id = " + str(check_user)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                # Inform the user about toggle
                                send_message(check_user, message, True)

                            # The user wants to toggle workday notifications
                            if splitted[0] == "/toggle_leave_notifications":
                                # Toggle setting
                                if get_setting_leave_messages(check_user) is True:
                                    message = "You will no longer get notifications if the last one leaves the Discord channel!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET leave_messages = 'False' WHERE telegram_id = " + str(check_user)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                else:
                                    message = "You will now get notifications if the last one leaves the Discord channel!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET leave_messages = 'True' WHERE telegram_id = " + str(check_user)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                # Inform the user about toggle
                                send_message(check_user, message, True)

                            # The user is lonely
                            if splitted[0] == "/Yes_i_am_lonely":
                                # Tell the user that everything is alright and that help might come.
                                message = "Everything is okay. Come Online, the other guys were contacted and should be on their way."
                                send_message(check_user, message, True)
                                # Send the other guys a message
                                lonely_person_username = get_username(check_user)
                                for notify_user in get_enabled_users():
                                    notify_user_username = get_username(notify_user)
                                    if not lonely_person_username == notify_user_username:
                                        message = "Hey {}, there is a lonely {} that need some love. Come into Discord to help him out.".format(notify_user_username, lonely_person_username)
                                        send_message(notify_user, message, True)

                            # The user is not lonely
                            if splitted[0] == "/No_i_am_not":
                                # Tell the user that everything is alright and that help might come.
                                message = "You can fool yourself but not me! Come Online, the other guys were contacted and should be on their way."
                                send_message(check_user, message, True)
                                # Send the other guys a message
                                lonely_person_username = get_username(check_user)
                                for notify_user in get_enabled_users():
                                    notify_user_username = get_username(notify_user)
                                    if not lonely_person_username == notify_user_username:
                                        message = "Hey {}, there is a lonely {} that need some love. Come into Discord to help him out.".format(notify_user_username, lonely_person_username)
                                        send_message(notify_user, message, True)

                            # User wants to set or change his Discord username
                            if splitted[0] == "/set_discord_username":
                                # Check if username was given
                                try:
                                    new_discord_user_name = splitted[1]
                                    # Update Discord username in database
                                    sqlquery = "UPDATE users SET discord_username = '{}' WHERE telegram_id = '{}'".format(new_discord_user_name, check_user)
                                    cursor = db.cursor()
                                    cursor.execute(sqlquery)
                                    db.commit()
                                    # Inform the user
                                    message = "Your Discord username was set to {}".format(new_discord_user_name)
                                    send_message(check_user, message, True)
                                except IndexError:
                                    message = "Please use [ /set_discord_username YOUR-USERNAME ]"
                                    send_message(check_user, message, True)

                            # User wants to broadcast a message
                            if splitted[0] == "/on_the_way" or splitted[0] == "/later" or splitted[0] == "/not_today":
                                # Confirm to the user
                                message = "Send message to the other fools!"
                                send_message(check_user, message, True)

                                # Write user status to database
                                cursor = db.cursor()
                                sqlquery = "UPDATE users SET day_status = '{}' WHERE telegram_id = '{}'".format(splitted[0], check_user)
                                cursor.execute(sqlquery)
                                sqlquery = "UPDATE users SET day_status_day = '{}' WHERE telegram_id = '{}'".format(checktime("day"), check_user)
                                cursor.execute(sqlquery)
                                db.commit()

                                # Send the other guys a message
                                reply_person_username = get_username(check_user)
                                for notify_user in get_enabled_users():
                                    notify_user_username = get_username(notify_user)
                                    if not reply_person_username == notify_user_username:
                                        if splitted[0] == "/on_the_way":
                                            message = "Message from {}: On the Way!".format(reply_person_username)
                                            send_message(notify_user, message, False)
                                        if splitted[0] == "/later":
                                            message = "Message from {}: Will come on later today!".format(reply_person_username)
                                            send_message(notify_user, message, False)
                                        if splitted[0] == "/not_today":
                                            message = "Message from {}: Not today!".format(reply_person_username)
                                            send_message(notify_user, message, False)

                            # Update the message counter
                            message_counter = message_counter + 1

                        # Discard all other messages
                        except KeyError:
                            log(2,"Another type of message received")

                # Set new offset to acknowledge messages on the telegram api
                offset = str(bot_messages_json["result"][message_amount - 1]["update_id"] + 1)

            # Sleep some seconds
            await asyncio.sleep(5)

        # Chatch errors and log them to database
        except Exception as error:
            print(str(error))
            log(5,"Exception: {}".format(error))

        # Reset variables
        chat_list = []
        chat_list_user_names = []
        if checktime("hour") == 1:
            intraday_announced = False

# Get the loop going
client.loop.create_task(telegram_bridge())

# Start the actual bot
client.run(discord_token)

if (db.is_connected()):
    db.close()
    cursor.close()
    print("MySQL connection is closed")
