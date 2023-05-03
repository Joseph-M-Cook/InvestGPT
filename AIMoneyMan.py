from googleapiclient.discovery import build
from flask import Flask, request
import requests
import openai
import time
import json

app = Flask(__name__)

GROUPME_API_URL = "https://api.groupme.com/v3/bots/post"

# API Keys and Private IDs
openai.api_key = 'YOUR_OPENAI_API_KEY'
GOOGLE_DEV_KEY = 'YOUR_GOOGLE_DEV_KEY'
GOOGLE_CX_KEY = 'YOUR_GOOGLE_CX_KEY'
ALPHA_VANTAGE_KEY = 'YOUR_ALPHA_VANTAGE_KEY'

# Reference: https://github.com/VRSEN/chatgtp-bing-clone
class AIMoneyMan():
    # Function to initalize Google Custom Search API
    def __init__(self):
        self.service = build("customsearch", "v1", developerKey=GOOGLE_DEV_KEY)

    # Function to execute Google Search API with generated query
    def _search(self, query):
        response = (self.service.cse().list(q=query,cx=GOOGLE_CX_KEY,).execute())
        return response['items']

    # Function to construct Google query
    def _get_search_query(self, query):
        messages = [{"role": "system",
                     "content": "You are an assistant that helps to convert text into a web search engine query. "
                                "You output only 1 query for the latest message and nothing else."}]

        messages.append({"role": "user", "content": "Based on my previous messages, "
                                                    "what is the most relevant and general web search query for the text below?\n\n"
                                                    "Text: " + query + "\n\n"
                                                                       "Query:"})

        search_query = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0,
        )['choices'][0]['message']['content']

        return search_query.strip("\"")

    # Function to construct response
    def run_text(self, query):
        search_query = self._get_search_query(query)

        # add system message to the front
        messages = [{"role": "system",
                     "content": "You are a financial assistant that answers questions based on search results and "
                                "provides links at the end to relevant parts of your answer. Do not apologize or mention what you are not capable of, make your response very brief"}]

        # Construct prompt from search results
        prompt = "You are a financial assistant, Answer query using the information from the search results below: \n\n"
        results = self._search(search_query)
        for result in results:
            prompt += "Link: " + result['link'] + "\n"
            prompt += "Title: " + result['title'] + "\n"
            prompt += "Content: " + result['snippet'] + "\n\n"
        prompt += "\nRESPOND IN JSON Format with 'content' and 'sources', keep your response under 1200 chars"
        prompt += "\nQuery: " + query

        messages.append({"role": "user", "content": prompt})

        # Generate response
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.4,
            max_tokens = 350,

        )['choices'][0]['message']['content']

        return response


# Function to fetch live stock data from Alpha Vantage API
def get_stock_info(stock_symbol):
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={stock_symbol.lower()}&apikey={ALPHA_VANTAGE_KEY}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print(data)
        if data and 'Global Quote' in data and data['Global Quote']:
            price = float(data['Global Quote']['05. price'])
            change_percent = float(data['Global Quote']['10. change percent'].rstrip('%'))
            volume = int(data['Global Quote']['06. volume'])
            return price, change_percent, volume

    print(f"Error fetching stock data: {response.status_code}")
    return None, None, None

# Reference: https://github.com/ErikBoesen/eightball
# Function to process and send incoming message and handle cases
def process_message(message):
    text = message.get('text')
    sender_type = message.get('sender_type')
    bot_id = message.get('bot_id')

    if sender_type != 'bot':
        if text and '@AI Money Man' in text:
            bot = AIMoneyMan()
            msg = bot.run_text(text[len('@AI Money Man'):])
            data = json.loads(msg)

            sources = "Sources:\n"
            for i in data['sources']:
                sources += i + '\n'

            send_message(data['content'])
            time.sleep(.2)
            send_message(sources)

        if text and text[0] == '$':
            stock_symbol = text[1:]
            current_stock_price, day_gain_percent, trading_volume = get_stock_info(stock_symbol)
            if current_stock_price and day_gain_percent and trading_volume:
                yahoo_finance_link = f"https://finance.yahoo.com/quote/{stock_symbol}"

                send_message(f"🚀 ${stock_symbol.upper()}\n"
                             f"💵 Current Price: ${current_stock_price:.2f}\n"
                             f"📈 Day Gain: {day_gain_percent:.2f}%\n"
                             f"📊 Trading Volume: {trading_volume:,}"
                             f"\n{yahoo_finance_link}",
                             bot_id)
            else:
                send_message("Invalid stock symbol or unavailable data.", bot_id)


# Function to send plain text message into GroupMe
def send_message(text, bot_id):
    data = {
        "bot_id": bot_id,
        "text": text
    }
    return requests.post(GROUPME_API_URL, json=data).status_code


@app.route('/', methods=['POST'])
def groupme_bot():
    message = request.get_json()
    process_message(message)
    return "OK", 200
