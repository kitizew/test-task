STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
]

CITIES = [
    ("New York", "New York"), ("Los Angeles", "California"), ("Chicago", "Illinois"),
    ("Houston", "Texas"), ("Phoenix", "Arizona"), ("Philadelphia", "Pennsylvania"),
    ("San Antonio", "Texas"), ("San Diego", "California"), ("Dallas", "Texas"),
    ("San Jose", "California"), ("Austin", "Texas"), ("Jacksonville", "Florida"),
    ("Fort Worth", "Texas"), ("Columbus", "Ohio"), ("Charlotte", "North Carolina"),
    ("San Francisco", "California"), ("Indianapolis", "Indiana"),
    ("Seattle", "Washington"), ("Denver", "Colorado"),
    ("Washington", "District of Columbia"), ("Boston", "Massachusetts"),
    ("El Paso", "Texas"), ("Nashville", "Tennessee"), ("Detroit", "Michigan"),
    ("Oklahoma City", "Oklahoma"), ("Portland", "Oregon"), ("Las Vegas", "Nevada"),
    ("Memphis", "Tennessee"), ("Louisville", "Kentucky"), ("Baltimore", "Maryland"),
    ("Milwaukee", "Wisconsin"), ("Albuquerque", "New Mexico"), ("Tucson", "Arizona"),
    ("Fresno", "California"), ("Sacramento", "California"), ("Kansas City", "Missouri"),
    ("Atlanta", "Georgia"), ("Omaha", "Nebraska"), ("Raleigh", "North Carolina"),
    ("Miami", "Florida"), ("Minneapolis", "Minnesota"), ("Tampa", "Florida"),
    ("Pittsburgh", "Pennsylvania"), ("Cincinnati", "Ohio"), ("Cleveland", "Ohio"),
    ("Orlando", "Florida"), ("St. Louis", "Missouri"), ("Salt Lake City", "Utah"),
    ("Irvine", "California"), ("Plano", "Texas"),
]

US_LOCATIONS = (
    ["United States", "Remote, United States"]
    + [f"{s}, United States" for s in STATES]
    + [f"{c}, {s}, United States" for c, s in CITIES]
)