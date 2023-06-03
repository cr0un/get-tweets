import json
import requests
import argparse
import re
import time
from datetime import datetime


# Настройки Telegram
TELEGRAM_TOKEN = '...'
TELEGRAM_CHAT_ID = '...'


# All values stored here are constant, copy-pasted from the website
FEATURES_USER = '{"blue_business_profile_image_shape_enabled":true,' \
                '"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,' \
                '"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,' \
                '"responsive_web_graphql_timeline_navigation_enabled":true} '
FEATURES_TWEETS = '{"blue_business_profile_image_shape_enabled":true,' \
                  '"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,' \
                  '"responsive_web_graphql_timeline_navigation_enabled":true,' \
                  '"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,' \
                  '"tweetypie_unmention_optimization_enabled":true,"vibe_api_enabled":true,' \
                  '"responsive_web_edit_tweet_api_enabled":true,' \
                  '"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,' \
                  '"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,' \
                  '"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,' \
                  '"standardized_nudges_misinfo":true,' \
                  '"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":false,' \
                  '"interactive_text_enabled":true,"responsive_web_text_conversations_enabled":false,' \
                  '"longform_notetweets_rich_text_read_enabled":true,"responsive_web_enhance_cards_enabled":false} '

AUTHORIZATION_TOKEN = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs' \
                      '%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA '
HEADERS = {
    'authorization': 'Bearer %s' % AUTHORIZATION_TOKEN,
    # The Bearer value is a fixed value that is copy-pasted from the website
    # 'x-guest-token': None,
}

GET_USER_URL = 'https://twitter.com/i/api/graphql/sLVLhk0bGj3MVFEKTdax1w/UserByScreenName'
GET_TWEETS_URL = 'https://twitter.com/i/api/graphql/CdG2Vuc1v6F5JyEngGpxVw/UserTweets'
FIELDNAMES = ['id', 'tweet_url', 'name', 'user_id', 'username', 'published_at', 'content', 'views_count',
              'retweet_count', 'likes', 'quote_count', 'reply_count', 'bookmarks_count', 'medias']


class TwitterScraper:

    def __init__(self, username):
        # We do initiate requests Session, and we get the `guest-token` from the HomePage
        resp = requests.get("https://twitter.com/")
        self.gt = resp.cookies.get_dict().get("gt") or "".join(re.findall(r'(?<=\"gt\=)[^;]+', resp.text))
        assert self.gt
        HEADERS['x-guest-token'] = getattr(self, 'gt')
        # assert self.guest_token
        self.HEADERS = HEADERS
        assert username
        self.username = username

    def get_user(self):
        # We recover the user_id required to go ahead
        arg = {"screen_name": self.username, "withSafetyModeUserFields": True}

        params = {
            'variables': json.dumps(arg),
            'features': FEATURES_USER,
        }

        response = requests.get(
            GET_USER_URL,
            params=params,
            headers=self.HEADERS
        )

        try:
            json_response = response.json()
        except requests.exceptions.JSONDecodeError:
            print(response.status_code)
            print(response.text)
            raise

        result = json_response.get("data", {}).get("user", {}).get("result", {})
        legacy = result.get("legacy", {})

        return {
            "id": result.get("rest_id"),
            "username": self.username,
            "full_name": legacy.get("name")
        }

    def tweet_parser(
            self,
            user_id,
            full_name,
            tweet_id,
            item_result,
            legacy
    ):

        # It's a static method to parse from a tweet
        medias = legacy.get("entities").get("media")
        medias = ", ".join(["%s (%s)" % (d.get("media_url_https"), d.get('type')) for d in
                            legacy.get("entities").get("media")]) if medias else None

        return {
            "id": tweet_id,
            "tweet_url": f"https://twitter.com/{self.username}/status/{tweet_id}",
            "name": full_name,
            "user_id": user_id,
            "username": self.username,
            "published_at": legacy.get("created_at"),
            "content": legacy.get("full_text"),
            "views_count": item_result.get("views", {}).get("count"),
            "retweet_count": legacy.get("retweet_count"),
            "likes": legacy.get("favorite_count"),
            "quote_count": legacy.get("quote_count"),
            "reply_count": legacy.get("reply_count"),
            "bookmarks_count": legacy.get("bookmark_count"),
            "medias": medias
        }

    def iter_tweets(self, limit=120):
        # The main navigation method
        print(f"[+] scraping: {self.username}")
        _user = self.get_user()
        full_name = _user.get("full_name")
        user_id = _user.get("id")
        if not user_id:
            print("/!\\ error: no user id found")
            raise NotImplementedError
        cursor = None
        _tweets = []

        while True:
            var = {
                "userId": user_id,
                "count": 100,
                "cursor": cursor,
                "includePromotedContent": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
                "withV2Timeline": True
            }

            params = {
                'variables': json.dumps(var),
                'features': FEATURES_TWEETS,
            }

            response = requests.get(
                GET_TWEETS_URL,
                params=params,
                headers=self.HEADERS,
            )

            json_response = response.json()
            result = json_response.get("data", {}).get("user", {}).get("result", {})
            timeline = result.get("timeline_v2", {}).get("timeline", {}).get("instructions", {})
            entries = [x.get("entries") for x in timeline if x.get("type") == "TimelineAddEntries"]
            entries = entries[0] if entries else []

            for entry in entries:
                content = entry.get("content")
                entry_type = content.get("entryType")
                tweet_id = entry.get("sortIndex")
                if entry_type == "TimelineTimelineItem":
                    item_result = content.get("itemContent", {}).get("tweet_results", {}).get("result", {})
                    legacy = item_result.get("legacy")
                    tweet_data = self.tweet_parser(user_id, full_name, tweet_id, item_result, legacy)
                    _tweets.append(tweet_data)

                if entry_type == "TimelineTimelineCursor" and content.get("cursorType") == "Bottom":
                    cursor = content.get("value")

                if len(_tweets) >= limit:
                    # We do stop — once reached tweets limit provided by user
                    break

            print(f"[#] tweets scraped: {len(_tweets)}")

            if len(_tweets) >= limit or cursor is None or len(entries) == 2:
                break

        return _tweets


def send_message(chat_id: str, tweet_url: str, content: str, token: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    message_text = f"{content}\n{tweet_url}"
    payload = {
        'chat_id': chat_id,
        'text': message_text,
        'parse_mode': 'HTML'
    }
    response = requests.post(url, data=payload)

    # Проверка отправки
    if response.status_code != 200:
        print(f"Failed to send message. Response: {response.content}")


def main():
    print('start')
    argparser = argparse.ArgumentParser()
    #  По умолчанию мы собираем последние 10 твитов
    argparser.add_argument('--limit', '-l', type=int, required=False, help='max tweets to scrape', default=10)
    args = argparser.parse_args()
    limit = args.limit

    assert limit

    # Аккаунты для отслеживания
    usernames = ['binance', 'krakenfx', 'bitfinex']
    all_tweets = set()

    while True:
        print(f'[{datetime.now()}] Checking for new tweets...')

        new_tweets = []
        max_tweets = 100  # Максимальное количество хранимых твитов

        for username in usernames:
            twitter_scraper = TwitterScraper(username)
            tweets = twitter_scraper.iter_tweets(limit=limit)
            assert tweets
            filtered_tweets = [tweet for tweet in tweets if
                               'maintenan' in tweet['content'].lower() and tweet['tweet_url'] not in all_tweets]
            all_tweets.update(tweet['tweet_url'] for tweet in filtered_tweets)
            if len(all_tweets) > max_tweets:
                oldest_tweets = sorted(all_tweets)[:len(all_tweets) - max_tweets]
                all_tweets.difference_update(oldest_tweets)
            new_tweets.extend(filtered_tweets)

        print(f'[{datetime.now()}] Found {len(new_tweets)} new tweets:')
        for tweet in new_tweets:
            tweet_url = tweet['tweet_url']
            content = tweet['content']
            published_at = datetime.strptime(tweet['published_at'], '%a %b %d %H:%M:%S %z %Y').strftime(
                '%Y-%m-%d %H:%M:%S')

            # Отправляем твит в телеграм
            send_message(TELEGRAM_CHAT_ID, tweet_url, content, published_at, TELEGRAM_TOKEN)

        # Время получения новых твитов (раз в час по умолчанию)
        time.sleep(3600)


if __name__ == '__main__':
    main()
