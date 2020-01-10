import datetime

class User:
    def __init__(self, name):
        self.name = name
        self.online = False
        self.online_since = False
        self.online_amount = datetime.timedelta(seconds=0)


def days_hours_minutes(td):
    return td.seconds//3600

def get_stats(db):
    # Prepare
    cursor = db.cursor()

    user_names = ["Oldmate", "r33n", "bugpeso", "BuGCab", "JagerVII", "vajori"]
    user_list = []
    day_stats = []
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    output = ""

    for index in range(7):
        day_stats.append(datetime.timedelta(seconds=0))

    for user_name in user_names:
        user_object = User(user_name)
        user_list.append(user_object)

    # Get logs
    sqlquery = "SELECT * FROM messages WHERE (message_text like '%Now online:%' OR message_text like '%Now AFK:%') AND message_id > 13720 ORDER BY message_id"
    cursor.execute(sqlquery)
    records = cursor.fetchall()

    # Get User statistics
    for index, record in enumerate(records):

        splits = record[1].split("'")
        for split in splits:
            for user in user_list:
                if split == user.name:
                    if not user.online and len(splits) > 4:
                        user.online = True
                        user.online_since = record[2]

            for user in user_list:
                if user.name not in splits and "AFK" not in str(splits):
                    if user.online:
                        user.online = False
                        online_time = record[2] - user.online_since
                        user.online_amount = user.online_amount + online_time

                        # Add stats to the day-stats
                        day = int(record[2].strftime("%w"))
                        day_stats[day] = day_stats[day] + online_time

    # See who was online the most
    output = output + "\nOnline hours per user:\n----------------------"
    ranking = {}
    for user in user_list:
        online_amount = datetime.timedelta.total_seconds(user.online_amount)
        entry = {int(user.online_amount.total_seconds()/60/60): user.name}
        ranking.update(entry)

    for key, value in sorted(ranking.items(), key=lambda item: item[0], reverse=True):
        output = output + "\n" + str(value) + " " + str(key)

    # See which days are most crowded
    output = output + "\n\nOnline hours per day:\n---------------------"

    # Shift List
    day_stats.append(day_stats.pop(0))
    day_ranking = {}
    for index, day_stat in enumerate(day_stats):
        entry = {int(day_stat.total_seconds()/60/60): day_names[index]}
        day_ranking.update(entry)

    for key, value in sorted(day_ranking.items(), key=lambda item: item[0], reverse=True):
        output = output + "\n" + str(value) + " " + str(key)

    return output
