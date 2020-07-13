import discord
import asyncio
import requests
import mysql.connector
import time
from datetime import datetime, date
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
bot_restarted = True
offset = "-0"
logs = []
last_log = 0
intraday_announced = False
user_list = []
datetimeFormat = '%Y-%m-%d %H:%M:%S'
unpaired_user = []
active_channels = []

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

# Get main discord channel from database
sqlquery = "select room_id from discord_channel where main = 'True'"
cursor.execute(sqlquery)
records = cursor.fetchone()
main_channel_id = int(records["room_id"])

# Get discord chat channel from database
sqlquery = "select room_id from discord_channel where chat = 'True'"
cursor.execute(sqlquery)
records = cursor.fetchone()
chat_channel_id = int(records["room_id"])

# Get active discord channels from database
sqlquery = "select room_id from discord_channel where active = 'True'"
cursor.execute(sqlquery)
records = cursor.fetchall()
for record in records:
    active_channels.append(int(record["room_id"]))

####################
# Database methods #
####################

# Checks if a given user wants to get the message that the last one left discord.
# Returns True or False
def get_setting_leave_messages(telegram_id_func):
    try:
        sqlquery = "select leave_messages from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        if not records["leave_messages"]:
            return False
        else:
            return True
    except Exception as error:
        print("Error:", error)
        return True

# Converts a given Telegram ID to the username
# Returns the Username
def get_username(telegram_id):
    for user in user_list:
        if user.telegram_id == telegram_id:
            return user.name
    else:
        return telegram_id

# Checks if a user wants to suppress messages based on the current time
# Returns True or False
def get_suppress_status(telegram_id_func):
    try:
        # Get database entry for user
        sqlquery = "select suppress from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()

        # If User wants to suppress check the time
        if records["suppress"] and checktime("day") < 5 and (checktime("hour") < 18 or checktime("hour") > 22):
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
        if records["suppress"]:
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
        sqlquery = "select day_status, day_status_day from users where telegram_id = {}".format(telegram_id_func)
        cursor.execute(sqlquery)
        records = cursor.fetchone()
        if records["day_status_day"] == str(date.today()):
            if records["day_status"] != "None":
                # Return the day_status
                return records["day_status"]
            else:
                return False
        else:
            return False
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
def send_message(telegram_id, message_func, force):

    # Check if user has a custom time window for today
    if get_today_window_state(telegram_id) and (checktime("hour") < get_today_window_start(telegram_id) or checktime("hour") > get_today_window_end(telegram_id)) and not force:
        # suppress if Monday - Friday and not between 18 and 23
        message = "Suppressed message for {} due to custom user setting for today".format(get_username(telegram_id))
        log(1, message)

    # Check if user wants to suppress notifications on workdays in general
    # suppress if Monday - Friday and not between 18 and 23
    elif get_suppress_status(telegram_id) and not get_today_window_state(telegram_id) and not force:
        message = "Suppressed message for {}".format(get_username(telegram_id))
        log(1, message)

    # suppress since user will not come online today
    elif get_day_status(telegram_id) == "/not_today" and not force:
        message = "Suppressed message for {} due to day_status".format(get_username(telegram_id))
        log(1, message)

    # Some messages like bot replies to the user need to be forced
    else:
        try:
            # Send message
            message = "Send message to {}: {}".format(get_username(telegram_id), message_func)
            log(1, message)
            requests.get("https://api.telegram.org/bot" + str(tgbot_token) + "/sendMessage?chat_id=" + str(telegram_id) + "&text=" + str(message_func))
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
        for user in user_list:
            user_day_status = get_day_status(user.telegram_id)
            if user_day_status:
                message = message + "\n" + user.name + "'s Status: " + user_day_status

    if not simple:
        message = message + "\nMessage: /on_my_way  /later  /not_today  /notsurebutitry"

    return message

# Checks if a given user is online by discords user ID
# Returns True or False
def is_user_in_channel_by_discord_id(discord_user_id, discord_online_users):
    for discord_online_user in discord_online_users:
        if str(discord_user_id) == str(discord_online_user.id):
            return True
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
    def __init__(self, telegram_id, name, enabled, discord_username, last_online_time, discord_user_id):
        self.telegram_id = telegram_id
        self.name = name
        self.is_enabled = enabled
        self.discord_username = discord_username
        self.is_online = False
        self.last_online_time = last_online_time
        self.discord_user_id = discord_user_id

# Get enabled users from database
sqlquery = "select * from users"
cursor.execute(sqlquery)
records = cursor.fetchall()

# Create list of active users
for user in records:
    user_object = User(user["telegram_id"],
                       user["user_name"],
                       user["enabled"],
                       user["discord_username"],
                       user["last_online_time"],
                       user["discord_user_id"])

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
            # Get online member list for active channels
            members = []
            for channel in active_channels:
                voice_channel = client.get_channel(channel)
                members = members + voice_channel.members

            # Check if all connected user are known
            for member in members:
                unknown_user = True
                for user in user_list:
                    if str(member.id) == str(user.discord_user_id):
                        unknown_user = False
                        break
                # Convert unknown user to known user
                if unknown_user:
                    log(2, "Unknown user joined the channel: {}".format(member.name))
                    new_user = User(None, member.name, False, member.name, datetime.now().strftime(datetimeFormat), member.id)
                    user_list.append(new_user)
                    # Insert into the database
                    # Insert new user to database
                    sqlquery = "INSERT INTO users (user_name, discord_username, discord_user_id) VALUES (\"{}\",\"{}\",\"{}\")".format(member.name, member.name, member.id)
                    cursor.execute(sqlquery)
                    db.commit()

            if bot_restarted:
                # Verbose for cli
                log(2, get_online_status(main_channel_id, True, True))

            # Update user online status
            # This only happens as the user connects to the channel
            for user in user_list:
                if not user.is_online and is_user_in_channel_by_discord_id(user.discord_user_id, members):
                    # User just connected to the voice channel
                    user.is_online = True

                    # Verbose for cli
                    log(2, get_online_status(main_channel_id, True, True))

                    # Clear day_status
                    sqlquery = "UPDATE users SET day_status = 'None' WHERE telegram_id = '{}'".format(user.telegram_id)
                    cursor.execute(sqlquery)
                    db.commit()

                    # Update discord_username if changed
                    check_discord_username = client.get_user(int(user.discord_user_id))
                    if user.discord_username != check_discord_username.name:
                        user.discord_username = check_discord_username.name
                        # Update in database
                        sqlquery = "UPDATE users SET discord_username = '{}' WHERE discord_user_id = '{}'".format(
                            user.discord_username, user.discord_user_id)
                        cursor.execute(sqlquery)
                        db.commit()

                    # Send out message for new online user
                    # Check if bot got restarted
                    if not bot_restarted:
                        # Check if it is only a reconnect (under 15 minutes)
                        diff = False
                        if user.last_online_time:
                            now = datetime.now().strftime(datetimeFormat)
                            diff = datetime.strptime(now, datetimeFormat) - datetime.strptime(user.last_online_time, datetimeFormat)
                        if not diff or diff.seconds > 60*15:
                            # Check who needs to get the message
                            for user in user_list:
                                if user.is_enabled and not user.is_online:
                                    message = get_online_status(main_channel_id, True, False)
                                    send_message(user.telegram_id, message, False)
                        else:
                            log(2, "{} just reconnected after {}".format(user.discord_username, diff))

                # User disconnected from voice channel
                elif user.is_online and not is_user_in_channel_by_discord_id(user.discord_user_id, members):
                    # Set last online time to database
                    user.last_online_time = datetime.now().strftime(datetimeFormat)
                    sqlquery = "UPDATE users SET last_online_time = '{}' WHERE telegram_id = '{}'".format(user.last_online_time, user.telegram_id)
                    cursor.execute(sqlquery)
                    db.commit()

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
                            for user in user_list:
                                # Check that the user is not online
                                if user.is_enabled and not user.is_online:
                                    # User with suppress enabled getting notified
                                    if get_suppress_config(user.telegram_id):
                                        message = get_online_status(main_channel_id, True, False)
                                        if "Nobody is online, you are on your own!" not in message:
                                            send_message(user.telegram_id, message, False)
                                    # User was not suppressed
                                    else:
                                        log(2, "{} was not suppressed and does not need to be notified!".format(user.discord_username))
                                # User is online
                                else:
                                    log(2, "{} is online and does not need to be notified!".format(user.discord_username))
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
                            bot_messages_text_single = str(bot_messages_json["result"][message_counter]["message"]["text"])
                            log(5, bot_messages_json)

                            # Check who wrote the message
                            telegram_id = str(bot_messages_json["result"][message_counter]["message"]["from"]["id"])
                            telegram_msg_user_name = str(bot_messages_json["result"][message_counter]["message"]["from"]["first_name"])

                            # Log the message
                            log(1, "New Message from {}: {}".format(get_username(telegram_id), bot_messages_text_single))

                            # If unknown User
                            if get_username(telegram_id) == telegram_id and telegram_id not in unpaired_user:
                                # Welcome the new User
                                message = "Hello {}, seems you are new here. Welcome!\n" \
                                          "You need to pair your Discord User!\n" \
                                          "[ /pair_discord YOUR-DISCORD-USERNAME ]\nOR\n" \
                                          "[ /pair_discord YOUR-DISCORD-ID ]".format(telegram_msg_user_name)
                                send_message(telegram_id, message, True)

                                # Remember user until connected
                                unpaired_user.append(telegram_id)

                            # Check for commands
                            # Split message by " " to be able to parse it easier
                            splitted = bot_messages_text_single.split(' ')

                            # The user wants to get messages
                            if splitted[0] == "/enable":
                                # Tell the user that he will get messages now
                                message = "You will now receive messages"
                                send_message(telegram_id, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = '1' WHERE telegram_id = " + str(telegram_id)
                                cursor.execute(sqlquery)
                                db.commit()
                                # Update User-Object
                                for user in user_list:
                                    if user.telegram_id == telegram_id:
                                        user.is_enabled = True

                            # The user does not want to get messages
                            if splitted[0] == "/disable":
                                # Tell the user that he will no longer get messages
                                message = "You will no longer receive messages"
                                send_message(telegram_id, message, True)
                                # Update Database
                                sqlquery = "UPDATE users SET enabled = '0' WHERE telegram_id = " + str(telegram_id)
                                cursor.execute(sqlquery)
                                db.commit()
                                # Update User-Object
                                for user in user_list:
                                    if user.telegram_id == telegram_id:
                                        user.is_enabled = False

                            # The user wants to now who is online
                            if splitted[0] == "/who_is_online":
                                # Tell the user who is online right now
                                message = get_online_status(main_channel_id, True, False)
                                send_message(telegram_id, message, True)

                            # The user wants to toggle workday notifications
                            if splitted[0] == "/toggle_workday_notifications":
                                # Toggle setting
                                if get_suppress_status(telegram_id):
                                    message = "You will get notification all day long!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET suppress = '0' WHERE telegram_id = " + str(telegram_id)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                else:
                                    message = "You will get notification on weekends and on workdays between 18-23 o'clock!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET suppress = '1' WHERE telegram_id = " + str(telegram_id)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                # Inform the user about toggle
                                send_message(telegram_id, message, True)

                            # The user wants to toggle workday notifications
                            if splitted[0] == "/toggle_leave_notifications":
                                # Toggle setting
                                if get_setting_leave_messages(telegram_id):
                                    message = "You will no longer get notifications if the last one leaves the Discord channel!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET leave_messages = '0' WHERE telegram_id = " + str(telegram_id)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                else:
                                    message = "You will now get notifications if the last one leaves the Discord channel!"
                                    # Update Database
                                    sqlquery = "UPDATE users SET leave_messages = '1' WHERE telegram_id = " + str(telegram_id)
                                    cursor.execute(sqlquery)
                                    db.commit()
                                # Inform the user about toggle
                                send_message(telegram_id, message, True)

                            # The user is lonely
                            if splitted[0] == "/Yes_i_am_lonely":
                                # Tell the user that everything is alright and that help might come.
                                message = "Everything is okay. Come Online, the other guys were contacted and should be on their way."
                                send_message(telegram_id, message, True)
                                # Send the other guys a message
                                lonely_person_username = get_username(telegram_id)
                                for user in user_list:
                                    if not lonely_person_username == user.name and not user.is_online and user.is_enabled:
                                        message = "Hey {}, there is a lonely {} that need some love. Come into Discord to help him out.".format(user.name, lonely_person_username)
                                        send_message(user.telegram_id, message, True)

                            # User wants to set or change his Discord username
                            if splitted[0] == "/pair_discord":
                                # Check if a valid discord id or username was given
                                try:
                                    discord_connect = splitted[1]
                                    user_found = False
                                    for user in user_list:
                                        if discord_connect == user.discord_username:
                                            user.telegram_id = telegram_id
                                            # Update user in database
                                            sqlquery = "UPDATE users SET telegram_id = '{}' WHERE discord_username = '{}'".format(telegram_id, user.discord_username)
                                            cursor.execute(sqlquery)
                                            db.commit()
                                            # Inform the user
                                            message = "Your Discord is connected now!\n" \
                                                      "You can use the commands /enable\n" \
                                                      "or /disable and /who_is_online - Just try!\n" \
                                                      "Messages on default will only be send workdays between 18 and 23 o'clock.\n" \
                                                      "You can change this with /toggle_workday_notifications\n" \
                                                      "Let the other know whats up today.\n" \
                                                      "Message: /on_my_way  /later  /not_today  /notsurebutitry"
                                            send_message(telegram_id, message, True)
                                            user_found = True
                                            break

                                        elif str(discord_connect) == str(user.discord_user_id):
                                            user.telegram_id = telegram_id
                                            # Update user in database
                                            sqlquery = "UPDATE users SET telegram_id = '{}' WHERE discord_user_id = '{}'".format(telegram_id, user.discord_user_id)
                                            cursor.execute(sqlquery)
                                            db.commit()
                                            # Inform the user
                                            message = "Your Discord is connected now!\n" \
                                                      "You can use the commands /enable\n" \
                                                      "or /disable and /who_is_online - Just try!\n" \
                                                      "Messages on default will only be send workdays between 18 and 23 o'clock.\n" \
                                                      "You can change this with /toggle_workday_notifications\n" \
                                                      "Let the other know whats up today.\n" \
                                                      "Message: /on_my_way  /later  /not_today  /notsurebutitry"
                                            send_message(telegram_id, message, True)
                                            user_found = True
                                            break

                                    # User was not found
                                    if not user_found:
                                            message = "I could not find you. Please check your input or ask the admin."
                                            send_message(telegram_id, message, True)

                                except IndexError:
                                    message = "Please use [ /pair_discord YOUR-DISCORD-USERNAME ]\n" \
                                              "Or use [ /pair_discord YOUR-DISCORD-ID ]"
                                    send_message(telegram_id, message, True)

                            # User wants to broadcast a status
                            if splitted[0] == "/on_my_way" or splitted[0] == "/later" or splitted[0] == "/not_today" or splitted[0].lower() == "/notsurebutitry":

                                # Write user status to database
                                sqlquery = "UPDATE users SET day_status = '{}' WHERE telegram_id = '{}'".format(splitted[0], telegram_id)
                                cursor.execute(sqlquery)
                                sqlquery = "UPDATE users SET day_status_day = '{}' WHERE telegram_id = '{}'".format(date.today(), telegram_id)
                                cursor.execute(sqlquery)
                                db.commit()

                                # Send the other guys a message
                                reply_person_username = get_username(telegram_id)
                                for user in user_list:
                                    if not reply_person_username == user.name and user.is_enabled:
                                        if splitted[0] == "/on_my_way":
                                            message = "Message from {}: On the Way!".format(reply_person_username)
                                            send_message(user.telegram_id, message, False)
                                        if splitted[0] == "/later":
                                            message = "Message from {}: Will come on later today!".format(reply_person_username)
                                            send_message(user.telegram_id, message, False)
                                        if splitted[0] == "/not_today":
                                            message = "Message from {}: Not today!".format(reply_person_username)
                                            send_message(user.telegram_id, message, False)
                                        if splitted[0].lower() == "/notsurebutitry":
                                            message = "Message from {}: Not sure but i try!".format(reply_person_username)
                                            send_message(user.telegram_id, message, False)

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
                                            .format(telegram_id, time_window_day, time_window_start, time_window_end, time_window_start, time_window_end)

                                        cursor.execute(sqlquery)
                                        db.commit()

                                        # Inform the user
                                        message = "Your new time window seems valid, good job!"
                                        send_message(telegram_id, message, True)

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
                                    send_message(telegram_id, message, True)

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
                                        send_message(telegram_id, message, True)

                                    else:
                                        # If the user did not give a valid time window jump to exception message
                                        raise Exception

                                # The user did not give a valid time window
                                except Exception as error:
                                    log(5, "Exception: {}".format(error))

                                    message = "Please use [ /set_verbosity level ]\n" \
                                              "Level can be: 0-9"
                                    send_message(telegram_id, message, True)

                            # The user wants to get the stats
                            if splitted[0] == "/show_stats":
                                # Tell the user the stats
                                message = discordstats.get_stats(db)
                                send_message(telegram_id, message, True)

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
            print("Sleep 10 secs after error!")
            time.sleep(10)

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
