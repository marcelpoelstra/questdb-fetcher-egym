"""Hand-written API responses in the shape of the connector's JSON, with invented values."""

import datetime

NOW = datetime.datetime(2026, 9, 27, 6, 0, tzinfo=datetime.timezone.utc)

EXERCISE_MACHINE = {
    "id": 1001,
    "activity": {"activityId": 581, "category": "EGYM_MACHINE", "name": {"en": "EGYM Leg Press"}},
    "sets": [
        {
            "setType": "REP_BASED",
            "numberOfReps": 12,
            "weight": 50.0,
            "duration": 60,
            "distance": None,
            "heartRate": None,
            "speed": None,
            "incline": None,
            "recoveryTime": None,
            "trainingMethod": "REGULAR_REPBASED",
            "sideMode": "BOTH",
        },
        {
            "setType": "REP_BASED",
            "numberOfReps": 10,
            "weight": 52.5,
            "duration": 55,
            "distance": None,
            "heartRate": None,
            "speed": None,
            "incline": None,
            "recoveryTime": None,
            "trainingMethod": "REGULAR_REPBASED",
            "sideMode": "BOTH",
        },
    ],
    "completedAt": "2026-01-15T18:30:00.25",
    "timezone": "Europe/Berlin",
    "sourceType": "FITNESS_MACHINE_SOURCE",
    "source": None,
    "kiloCalories": 15.0,
    "points": 12,
    "summary": {
        "totalDuration": None,
        "totalDistance": None,
        "verticalDistance": None,
        "avgPace": None,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgSpeed": None,
        "avgIncline": None,
    },
}

EXERCISE_WALK = {
    "id": 1002,
    "activity": {"activityId": 1120, "category": "CARDIO_OUTDOOR", "name": {"en": "Walking Outdoor"}},
    "sets": [
        {
            "setType": "TIME_BASED",
            "numberOfReps": None,
            "weight": None,
            "duration": 1800,
            "distance": 2500.0,
            "heartRate": None,
            "speed": 1.4,
            "incline": None,
            "recoveryTime": None,
            "trainingMethod": None,
            "sideMode": None,
        }
    ],
    "completedAt": "2026-07-15T18:30:00",
    "timezone": "Europe/Amsterdam",
    "sourceType": "CONNECTED_APP",
    "source": "WITHINGS",
    "kiloCalories": 88.5,
    "points": 70,
    "summary": {
        "totalDuration": 1800,
        "totalDistance": 2500.0,
        "verticalDistance": None,
        "avgPace": None,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgSpeed": 1.4,
        "avgIncline": None,
    },
}

WORKOUTS = [
    {"completedAt": "2026-01-15T18:30:00.25", "timezone": "Europe/Berlin", "exercises": [EXERCISE_MACHINE]},
    {"completedAt": "2026-07-15T18:30:00", "timezone": "Europe/Amsterdam", "exercises": [EXERCISE_WALK]},
]

LATEST_BODY_METRICS = [
    {"type": "WEIGHT_KG", "value": 80.5, "createdAt": "2026-02-01T07:15:30.5Z", "source": "MANUAL"},
    {"type": "HEIGHT_CM", "value": 180.0, "createdAt": "2026-02-01T07:15:30.5Z", "source": "MANUAL"},
]

BODY_MEASUREMENTS = [
    {
        "id": 2001,
        "createdAt": "2026-02-01T07:15:30.5",
        "source": "MANUAL",
        "sourceLabel": None,
        "metrics": [
            {"type": "WEIGHT_KG", "value": 80.5, "valueInterpretation": "UNDEFINED"},
            {"type": "HEIGHT_CM", "value": 180.0, "valueInterpretation": None},
        ],
    }
]

CARDIO_BLOOD_PRESSURE = {
    "measurements": [
        {
            "id": 3001,
            "createdAt": "2026-03-01T06:30:00Z",
            "timezone": "Europe/Berlin",
            "source": "MANUAL",
            "sourceLabel": None,
            "metrics": [{"type": "SYSTOLIC_PRESSURE", "value": 125.0}, {"type": "DIASTOLIC_PRESSURE", "value": 80.0}],
        }
    ]
}

CARDIO_RESTING_HEART_RATE = {
    "measurements": [
        {
            "id": 3002,
            "createdAt": "2026-03-02T05:28:53.12Z",
            "timezone": "Europe/Berlin",
            "source": "MOBILE_APP",
            "sourceLabel": "Apple Health",
            "metrics": [{"type": "RESTING_HEART_RATE", "value": 60.0}],
        }
    ]
}

STRENGTH = {
    "strengthMeasurements": [
        {
            "id": 4001,
            "createdAt": "2026-04-01T16:22:53.7Z",
            "timezone": "Europe/Berlin",
            "activity": {"activityId": 997, "label": "EGYM Leg Curl"},
            "bodyRegion": "LOWER",
            "source": "FITNESS_MACHINE",
            "sourceLabel": "Fitness Machine",
            "strength": {"value": 70},
            "strengthSet": {"reps": 1, "weight": 70.5},
        }
    ]
}

BIO_AGE_SUMMARY = {
    "rangeStart": "2026-01-01",
    "rangeEnd": "2026-12-31",
    "totalBioAge": [{"date": "2026-01-01", "value": 45}],
    "muscleBioAge": [{"date": "2026-02-01", "value": 40}],
    "metabolicBioAge": [],
    "cardioBioAge": [],
    "flexibilityBioAge": [],
}

EMPTY_BIO_AGE_SUMMARY = {
    "rangeStart": "2026-01-01",
    "rangeEnd": "2026-12-31",
    "totalBioAge": [],
    "muscleBioAge": [],
    "metabolicBioAge": [],
    "cardioBioAge": [],
    "flexibilityBioAge": [],
}

MUSCLE_IMBALANCES = {
    "muscleImbalances": [
        {
            "calculatedAt": "2026-07-01T16:21:21.048",
            "timezone": "Europe/Berlin",
            "agonistMuscle": "QUADRICEPS",
            "antagonistMuscle": "HAMSTRING",
            "position": 3900.5,
            "optimalRangeStartPosition": 4000.0,
            "optimalRangeEndPosition": 6000.0,
            "rangeSize": 10000.0,
            "imageUrl": "",
            "bodyRegion": "LOWER",
            "agonistStrengthValue": 95,
            "antagonistStrengthValue": 70,
            "agonistActivityId": 994,
            "antagonistActivityId": 997,
        }
    ]
}

ACTIVITY_LEVEL = {"points": 1000, "daysLeft": 17, "level": "gold", "goal": 3900, "maintainPoints": 2300}

RANKING = {
    "rankOfUser": {
        "exerciserId": "00000000-0000-0000-0000-000000000001",
        "rank": {"value": 30},
        "points": {"value": 2500},
        "averageRank": 31,
        "totalNumberOfUsers": None,
    },
    "leaderBoard": {"items": [], "nextPageToken": None, "totalNumberOfUsers": 170},
}

GYMS = [
    {
        "uuid": "00000000-0000-0000-0000-00000000aaaa",
        "name": "Example Gym",
        "timezone": "Europe/Berlin",
        "url": "https://gym.example.com/",
    }
]

PROFILE = {
    "uuid": "00000000-0000-0000-0000-000000000001",
    "firstname": "Alex",
    "lastname": "Example",
    "birthday": "05/01/1980",
    "gender": "M",
}

FAVOURITES = [{"activityId": 1286, "category": "SPORT", "name": {"en": "Workout (General)"}}]

PLANS = [{"id": 5001, "name": "My training", "groupType": "USER_OWN", "type": "USER_TRAINING_PLAN"}]
