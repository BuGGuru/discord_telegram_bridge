import discord
import asyncio
import requests
import mysql.connector
import time
from datetime import datetime
import configparser
import discordstats

###########
# Configs #
###########

# Get database config
config = configparser.RawConfigParser()
config.read("./database.ini")
dbhost = config.get("Database", "dbhost")
database = config.get("Database", "database")
dbuser = config.get("Database", "dbuser")
dbpass = config.get("Database", "dbpass")

# Variables to work with
client = discord.Client()
members_old = ""
bot_restarted = True
offset = "-0"
logs = []
last_log = 0
intraday_announced = False
user_list = []

# Get the Database running
db = mysql.connector.connect(host=dbhost,
                             database=database,
                             user=dbuser,
                             password=dbpass)

cursor = db.cursor(dictionary=True, buffered=True)

# Get configs from database

# Discord token
sqlquery = "SELECT config_value FROM configs WHERE config_name = 'discord_token'"
cursor.execute(sqlquery)
records = cursor.fetchone()
discord_token = records["config_value"]

# Telegram token
sqlquery = "SELECT config_value FROM configs WHERE config_name = 'telegram_token'"
cursor.execute(sqlquery)
records = cursor.fetchone()
tgbot_token = records["config_value"]

# CLI verbosity
sqlquery = "SELECT config_value FROM configs WHERE config_name = 'cli_verbosity'"
cursor.execute(sqlquery)
records = cursor.fetchone()
cli_verbosity = int(records["config_value"])

# Get main discord channels from database
sqlquery = "select room_id from discord_channel where main = 'True'"
cursor.execute(sqlquery)
records = cursor.fetchone()
main_channel_id = int(records["room_id"])

####################
# Database methods #
####################

# Get the users with enabled notifications
# Returns a list with telegram chat IDs
def get_enabled_users():
    try:
        chat_list = []
        chat_list_user_names = []

        # Get enabled users from database
        sqlquery = "select * from users where enabled = 'True'"
        cursor.execute(sqlquery)
        records = cursor.fetchall()

        # Put them into a list
        for row in records:
            chat_list.append(row["telegram_id"])
            chat_list_user_names.append(row["user_name"])

        # Log and return the list
        log(3, "Enabled users: " + str(chat_list_user_names))
        return chat_list
    except:
        return False

# Checks if a given user wants to get the message that the last one left discord.
# Returns True or False
def get_setting_leave_messages(telegram_id_func):
    try:
        sqlquery = "select leave_messages from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        if records["leave_message"] == "False":
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
        return records["user_name"]
    except:
        return telegram_id_func

# Converts a given Telegram chat ID to the bot-username
# Returns the Discord-Username
def get_discord_username(telegram_id_func):
    try:
        sqlquery = "select discord_username from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        if records["discord_username"]:
            return records["discord_username"]
        else:
            return telegram_id_func
    except:
        return telegram_id_func

# Checks if a user wants to suppress messages based on the current time
# Returns True or False
def get_suppress_status(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select suppress from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        # If User wants to suppress check the time
        if records["suppress"] == "True" and checktime("day") < 5 and (checktime("hour") < 18 or checktime("hour") > 22):
            # User wants to suppress and its out of the notification time
            return True
        else:
            # User does not want to suppress or its in the notification time
            return False
    except:
        # If it is not set we assume it should be suppressed
        return True

# Checks if a user wants to suppress messages in general
# Returns True or False
def get_suppress_config(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select suppress from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        # If User wants to suppress check the time
        if records["suppress"] == "True":
            # User wants to suppress
            return True
        else:
            # User does not want to suppress
            return False
    except:
        # If it is not set we assume it should be suppressed
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
        return records["day_status"]
    except:
        # Return False if not set
        return False

def get_today_window_state(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select * from times where telegram_id = {} AND day = {}".format(telegram_id_func, checktime("day"))
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        # Return the day_status
        return records["telegram_id"]
    except:
        # Return False if not set
        return False

def get_today_window_start(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select start from times where telegram_id = {} AND day = {}".format(telegram_id_func, checktime("day"))
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        # Return the day_status
        return int(records["start"])
    except:
        # Return False if not set
        return False

def get_today_window_end(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select end from times where telegram_id = {} AND day = {}".format(telegram_id_func, checktime("day"))
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        # Return the day_status
        return int(records["end"])
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

    # Check if user has a custom time window for today
    if get_today_window_state(chat) and (checktime("hour") < get_today_window_start(chat) or checktime("hour") > get_today_window_end(chat)) and not force:
        # suppress if Monday - Friday and not between 18 and 23
        message = "Suppressed message for {} due to custom user setting for today".format(get_username(chat))
        log(1, message)

    # Check if user wants to suppress notifications on workdays in general
    # suppress if Monday - Friday and not between 18 and 23
    elif get_suppress_status(chat) and not get_today_window_state(chat) and not force:
        message = "Suppressed message for {} due to Day or Time".format(get_username(chat))
        log(1, message)

    # suppress since user will not come online today
    elif get_day_status(chat) == "/not_today" and not force:
        message = "Suppressed message for {} due to day_status".format(get_username(chat))
        log(1, message)

    # Some messages like bot replies to the user need to be forced
    else:
        try:
            # Send message
            message = "Send message to {}: {}".format(get_username(chat), message_func)
            log(1, message)
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
def get_online_status(channel, status, simple):
    # Main channel
    voice_channel = client.get_channel(channel)
    members = voice_channel.members
    member_list = []
    for member in members:
        member_list.append(member.name)

    # Construct Message
    if member_list:
        message = "Online: {}".format(member_list)

    else:
        if simple:
            message = "Online: {}".format(member_list)
        else:
            message = "Nobody is online, you are on your own!"

    if status:
        for user in get_enabled_users():
            user_day_status = get_day_status(user)
            if user_day_status and (get_discord_username(user) not in member_list):
                message = message + "\n" + get_username(user) + "'s Status: " + user_day_status

    if not simple:
        message = message + "\nMessage: /on_my_way  /later  /not_today  /notsurebutitry"

    return message

# Checks if a given user is online
# Returns True or False
def is_user_in_channel(telegram_id_func, channel):
    if get_discord_username(telegram_id_func) in get_online_status(channel, False, True):
        return True
    else:
        return False

################
# Misc methods #
################

# Log to console
def log(verbosity, output):
    global last_log

    if verbosity <= cli_verbosity:
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

##############
# user class #
##############

class User:
    def __init__(self, telegram_id, name, enabled):
        self.telegram_id = telegram_id
        self.name = name
        self.is_enabled = enabled
        self.is_online = False

# Get enabled users from database
sqlquery = "select * from users"
cursor.execute(sqlquery)
records = cursor.fetchall()

# Create list of active users
for user in records:
    user_object = User(user["telegram_id"],
                       user["user_name"],
                       user["enabled"])

    user_list.append(user_object)

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
    global members_old
    global bot_restarted
    global cursor
    global intraday_announced
    global cli_verbosity

    # Wait after restart till the bot is logged into discord
    await client.wait_until_ready()
    # Start the whole loop
    while not client.is_closed():
        try:
            # Check if we have a connection to the database or try to reconnect
            if not db.is_connected():
                cursor = db.cursor(dictionary=True, buffered=True)
                log(5, "Reconnected to Database")

            # Variables for the bot
            # Main channel
            voice_channel = client.get_channel(main_channel_id)
            members = voice_channel.members

            for member in members:
                known_user = False
                for user in user_list:
                    if member.name == user.name:
                        known_user = True
                if not known_user:
                    log(2, "Unknown user joined the channel: {}".format(member.name))
                    new_user = User(None, member.name, False)
                    user_list.append(new_user)

            if bot_restarted:
                # Verbose for cli
                log(2, get_online_status(main_channel_id, True, True))

            # Update user online status
            for user in user_list:
                if user.is_enabled and not user.is_online and is_user_in_channel(user.telegram_id, main_channel_id):
                    user.is_online = True
                    # Verbose for cli
                    log(2, get_online_status(main_channel_id, True, True))
                    # Send out message for new online user
                    # Check if bot got restarted
                    if not bot_restarted:
                        # Check who wants to get messages
                        for chat in get_enabled_users():
                            # Check if user is online
                            if not is_user_in_channel(chat, main_channel_id):
                                message = get_online_status(main_channel_id, True, False)
                                send_message(chat, message, False)
                            # If user is online he does not need to be notified
                            else:
                                log(2, "{} is online and does not need to be notified!".format(get_discord_username(chat)))

                elif user.is_online and not is_user_in_channel(user.telegram_id, main_channel_id):
                    user.is_online = False
                    log(2, "{} is now offline".format(user.name))
                    # Verbose for cli
                    log(2, get_online_status(main_channel_id, True, True))

            # Announce if someone is online and it turns 18 o'clock
            # Announce only to user that suppressed the messages before
            if not intraday_announced:
                if checktime("hour") == 18:
                    if not bot_restarted:
                            # Log Action
                            log(2, "Will announce online members to prior suppressed users.")

                            # Message users
                            for chat in get_enabled_users():
                                # Check that the user is not online
                                if not is_user_in_channel(chat, main_channel_id):
                                    # User with suppress enabled getting notified
                                    if get_suppress_config(chat):
                                        message = get_online_status(main_channel_id, True, False)
                                        send_message(chat, message, False)
                                    # User was not suppressed
                                    else:
                                        log(2, "{} was not suppressed and does not need to be notified!".format(get_discord_username(chat)))
                                # User is online
                                else:
                                    log(2, "{} is online and does not need to be notified!".format(get_discord_username(chat)))
                            intraday_announced = True
                    else:
                        intraday_announced = True

            # Update the variables for next loop
            if bot_restarted:
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
                # suppress old actions if bot restarted
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
                            log(5, bot_messages_json)

                            # Check who wrote the message
                            check_user = str(bot_messages_json["result"][message_counter]["message"]["from"]["id"])
                            check_user_name = str(bot_messages_json["result"][message_counter]["message"]["from"]["first_name"])

                            # Log the message
                            log(1, "New Message from {}: {}".format(get_username(check_user), bot_messages_text_single))

                            # Create new user if unknown
                            if get_username(check_user) == check_user:
                                # Insert new user to database
                                sqlquery = "INSERT INTO users (telegram_id, user_name) VALUES (\"{}\",\"{}\")".format(check_user, check_user_name)
                                cursor.execute(sqlquery)
                                db.commit()
                                log(2, "Created new User")
                                # Welcome the new User
                                message = "Hello {}, seems you are new here. Welcome!\nYou can use the commands /enable " \
                                          "or /disable and /who_is_online - Just try!\n" \
                                          "You should set your Discord Username with [ /set_discord_username YOUR-USERNAME ]\n" \
                                          "You can also suppress notifications on workdays between 18 and 23 o'clock with /toggle_workday_notifications\n" \
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
                                message = get_online_status(main_channel_id, True, False)
                                send_message(check_user, message, True)

                            # The user wants to toggle workday notifications
                            if splitted[0] == "/toggle_workday_notifications":
                                # Toggle setting
                                if get_suppress_status(check_user):
                                    message = "You will get notification all day long!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET suppress = 'False' WHERE telegram_id = " + str(check_user)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                else:
                                    message = "You will get notification on weekends and on workdays between 18-23 o'clock!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET suppress = 'True' WHERE telegram_id = " + str(check_user)
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
                                    cursor.execute(sqlquery)
                                    db.commit()
                                    # Inform the user
                                    message = "Your Discord username was set to {}".format(new_discord_user_name)
                                    send_message(check_user, message, True)
                                except IndexError:
                                    message = "Please use [ /set_discord_username YOUR-USERNAME ]"
                                    send_message(check_user, message, True)

                            # User wants to broadcast a message
                            if splitted[0] == "/on_my_way" or splitted[0] == "/later" or splitted[0] == "/not_today" or splitted[0].lower() == "/notsurebutitry":
                                # Confirm to the user
                                message = "Send message to the other fools!"
                                send_message(check_user, message, True)

                                # Write user status to database
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
                                        if splitted[0] == "/on_my_way":
                                            message = "Message from {}: On the Way!".format(reply_person_username)
                                            send_message(notify_user, message, False)
                                        if splitted[0] == "/later":
                                            message = "Message from {}: Will come on later today!".format(reply_person_username)
                                            send_message(notify_user, message, False)
                                        if splitted[0] == "/not_today":
                                            message = "Message from {}: Not today!".format(reply_person_username)
                                            send_message(notify_user, message, False)
                                        if splitted[0].lower() == "/notsurebutitry":
                                            message = "Message from {}: Not sure but i try!".format(reply_person_username)
                                            send_message(notify_user, message, False)

                            # User wants to set a time window for messages
                            if splitted[0] == "/set_time_window":
                                # Check if valid time window was given
                                try:
                                    # Split user data into pieces
                                    command_split = splitted[1].split(',')
                                    time_window_day = int(command_split[0])
                                    time_window_start = int(command_split[1])
                                    time_window_end = int(command_split[2])

                                    # Check data and update Database
                                    if time_window_day < 7 and time_window_start < 25 and time_window_start < 25:
                                        sqlquery = "INSERT INTO times (telegram_id, day, start, end) VALUES" \
                                                   " ('{}', '{}', '{}', '{}') ON DUPLICATE KEY UPDATE start = '{}', end = '{}'"\
                                            .format(check_user, time_window_day, time_window_start, time_window_end, time_window_start, time_window_end)

                                        cursor.execute(sqlquery)
                                        db.commit()

                                        # Inform the user
                                        message = "Your new time window seems valid, good job!"
                                        send_message(check_user, message, True)

                                    else:
                                        # If the user did not give a valid time window jump to exception message
                                        raise Exception

                                # The user did not give a valid time window
                                except Exception as error:
                                    log(5, "Exception: {}".format(error))

                                    message = "Please use [ /set_time_window day,start,end ]\n" \
                                              "Day = 0-6 for Monday-Sunday and start/end are hours from 1-24\n" \
                                              "Example: /set_time_window 2,12,23\n" \
                                              "For Wednesday between 12 and 23 o'clock"
                                    send_message(check_user, message, True)

                            # Admin wants to set the verbosity level
                            if splitted[0] == "/set_verbosity":
                                # Check if valid level was given
                                try:
                                    new_verbosity_level = int(splitted[1])

                                    # Check data
                                    if new_verbosity_level < 10:
                                        # Update Database
                                        sqlquery = "UPDATE configs SET config_value = '{}' WHERE config_name = 'cli_verbosity'".format(new_verbosity_level)
                                        cursor.execute(sqlquery)
                                        db.commit()

                                        # Set config
                                        cli_verbosity = new_verbosity_level

                                        # Inform the user
                                        message = "Set the verbosity level to: {}".format(new_verbosity_level)
                                        send_message(check_user, message, True)

                                    else:
                                        # If the user did not give a valid time window jump to exception message
                                        raise Exception

                                # The user did not give a valid time window
                                except Exception as error:
                                    log(5, "Exception: {}".format(error))

                                    message = "Please use [ /set_verbosity level ]\n" \
                                              "Level can be: 0-9"
                                    send_message(check_user, message, True)

                            # The user wants to get the stats
                            if splitted[0] == "/show_stats":
                                # Tell the user the stats
                                message = discordstats.get_stats(db)
                                send_message(check_user, message, True)

                            # Update the message counter
                            message_counter = message_counter + 1

                        # Discard all other messages
                        except KeyError:
                            log(2, "Another type of message received")

                # Set new offset to acknowledge messages on the telegram api
                offset = str(bot_messages_json["result"][message_amount - 1]["update_id"] + 1)

            # Sleep some seconds
            await asyncio.sleep(5)

        # Catch errors and log them to database
        except Exception as error:
            print(str(error))
            log(5, "Exception: {}".format(error))

        # Reset variables
        if checktime("hour") == 1:
            intraday_announced = False

# Get the loop going
client.loop.create_task(telegram_bridge())

# Start the actual bot
client.run(discord_token)

if db.is_connected():
    db.close()
    cursor.close()
    print("MySQL connection is closed")
