"""Common real-world canvas formats, used ONLY for testing and the demo.

The brief says hidden targets come from "a fixed catalogue of common
real-world formats". That catalogue isn't shipped, so this is our own
list of widely used sizes. The engine never looks at it: no layout logic
is keyed to a specific size.
"""

FORMATS = [
    {"key": "ig_post", "name": "Instagram Post", "width": 1080, "height": 1080},
    {"key": "ig_portrait", "name": "Instagram Portrait", "width": 1080, "height": 1350},
    {"key": "ig_story", "name": "Instagram Story", "width": 1080, "height": 1920},
    {"key": "pin", "name": "Pinterest Pin", "width": 1000, "height": 1500},
    {"key": "fb_post", "name": "Facebook Link Post", "width": 1200, "height": 630},
    {"key": "yt_thumb", "name": "YouTube Thumbnail", "width": 1280, "height": 720},
    {"key": "x_header", "name": "X Header", "width": 1500, "height": 500},
    {"key": "li_banner", "name": "LinkedIn Banner", "width": 1584, "height": 396},
    {"key": "billboard", "name": "Billboard Ad", "width": 970, "height": 250},
    {"key": "leaderboard", "name": "Leaderboard Ad", "width": 728, "height": 90},
    {"key": "mobile_banner", "name": "Mobile Banner", "width": 320, "height": 50},
    {"key": "med_rect", "name": "Medium Rectangle", "width": 300, "height": 250},
    {"key": "half_page", "name": "Half Page Ad", "width": 300, "height": 600},
    {"key": "skyscraper", "name": "Wide Skyscraper", "width": 160, "height": 600},
    {"key": "poster", "name": "Letter Poster", "width": 1275, "height": 1650},
]
