import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import pyodbc
import json



######ESTABLISHING SQL DATABASE CONNECTION####

#CLIENT INFO SECRETS



server = 'sweets-discord-bots.database.windows.net'
database = 'VocabularyDiscordBot'
username = ''
password =  ''
driver = '{ODBC Driver 18 for SQL Server}'


#CONNECTION

connection = f"""
    DRIVER={driver};
    SERVER={server};
    DATABASE={database};
    UID={username};
    PWD={password};
    Encrypt=yes;
    TrustServerCertificate=no;
    Connection Timeout=30;
"""


conn = pyodbc.connect(connection)

#LOADING TOKEN FROM SAFE LOCATION
load_dotenv()
TOKEN: str = os.getenv("DISCORD_TOKEN")

#BOT SETUP
intents= discord.Intents.default()
intents.message_content = True


#VOICE STATE EVENT ENABLED
#intents = discord.Intents.default()
#intents.voice_state = True

bot = commands.Bot(command_prefix="!", intents=intents)


##### TEXT CHAT VOCAB #####
user_stats = {}


def process_message(user_id, message):
    words = message.lower().split()  # Split message into individual words

    # Ensure that 'largest_words' is a list and 'frequent_words' is a dictionary
    user_data = user_stats.get(user_id, {"frequent_words": {}, "largest_words": [], "total_words": 0})

    # Retrieve 'frequent_words', 'largest_words', and 'total_words' from user_data
    frequent_words = user_data.get('frequent_words', {})
    largest_words = user_data.get('largest_words', [])
    total_words = user_data.get('total_words', 0)

    for word in words:
        # Count the frequency of each word
        if word in frequent_words:
            frequent_words[word] += 1
        else:
            frequent_words[word] = 1

        frequent_words = dict(sorted(frequent_words.items(), key=lambda item: item[1], reverse=True)[:5])

        # Track the largest words (keep top 5 largest words)
        if len(largest_words) < 5:
            largest_words.append(word)  # Append word to the largest_words list
        else:
            # Replace smallest word if the new word is larger
            largest_words = sorted(largest_words, key=len)
            if len(word) > len(largest_words[0]):
                largest_words[0] = word

        # Increment total word count
        total_words += 1

    # Update user data in user_stats
    user_stats[user_id] = {
        "frequent_words": frequent_words,
        "largest_words": largest_words,  # Ensure this is stored as a list
        "total_words": total_words
    }

    frequent_words_json = json.dumps(frequent_words)
    largest_words_json = json.dumps(largest_words)

    # Insert/Update the user's stats into the SQL database
    cursor = conn.cursor()

    cursor.execute("""
            IF EXISTS (SELECT 1 FROM UserStats WHERE user_id = ?)
            UPDATE UserStats
            SET frequent_words = ?, largest_words = ?, total_words = ?
            WHERE user_id = ?
            ELSE
            INSERT INTO UserStats (user_id, frequent_words, largest_words, total_words)
            VALUES (?, ?, ?, ?)
        """, user_id, frequent_words_json, largest_words_json, total_words, user_id,
                   user_id, frequent_words_json, largest_words_json, total_words)

    conn.commit()

@bot.event
async def on_message (message):
    if message.author == bot.user:
        return #Makes sure bot doesn't read its own messages

    #Skips message that are commands
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return


    #Stores and process the message contents


    process_message(message.author.id, message.content)

    await bot.process_commands(message) #Allows bot to function



##### STATISTICS ALGO #####

@bot.command()
async def vocabstat(ctx, user: discord.User = None):
    if not user:
        user = ctx.author

    cursor = conn.cursor()
    cursor.execute("SELECT frequent_words, largest_words, total_words FROM UserStats WHERE user_id = ?", user.id)
    row = cursor.fetchone()

    if row:
        frequent_words = json.loads(row[0]) if row[0] else {}
        largest_words = json.loads(row[1]) if row[1] else []
        total_words = row[2] if row[2] else 0

        if frequent_words or largest_words or total_words > 0:
            frequent_words_str = ', '.join(
                [f"{word} (x{count})" for word, count in frequent_words.items()]) or 'No words recorded'
            await ctx.send(f"**{user.name}'s Vocabulary Stats:**\n"
                           f"**Frequent Words:** {frequent_words_str}\n"
                           f"**Largest Words:** {', '.join(largest_words) if largest_words else 'No words recorded'}\n"
                           f"**Total Words:** {total_words}")
        else:
            await ctx.send(f"{user.name} has no recorded vocabulary data yet.")
    else:
        await ctx.send(f"No stats available for {user.name}.")


##### Ranking Command #####

@bot.command()
async def rank_vocab(ctx):
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, LEN(largest_words) FROM UserStats ORDER BY LEN(largest_words) DESC")
    rows = cursor.fetchall()

    if rows:
        ranking_message = "🌟 **Top 10 Users by Best Vocabulary:**\n"
        for index, row in enumerate(rows[:10]):
            user = bot.get_user(row[0])
            if user:
                ranking_message += f"**{index + 1}.** {user.name} - **Top Words Length:** {row[1]}\n"

        await ctx.send(ranking_message)
    else:
        await ctx.send("No ranking available yet.")


@bot.command()
async def rank_unique(ctx):
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, COUNT(DISTINCT frequent_words) FROM UserStats ORDER BY COUNT(DISTINCT frequent_words) DESC")
    rows = cursor.fetchall()

    if rows:
        ranking_message = "📊 **Top 10 Users by Unique Vocabulary:**\n"
        for index, row in enumerate(rows[:10]):
            user = bot.get_user(row[0])
            if user:
                ranking_message += f"**{index + 1}.** {user.name} - **Unique Words Count:** {row[1]}\n"

        await ctx.send(ranking_message)
    else:
        await ctx.send("No unique ranking available yet.")


#HANDELING BOT STARTUP
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


def main() -> None:
    bot.run(TOKEN)

if __name__ == '__main__':
    main()


