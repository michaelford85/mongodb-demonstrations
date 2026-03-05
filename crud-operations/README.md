# CRUD Demo: Add and Remove Movies (Python)

This demo adds a few fake movies to `sample_mflix.movies`, then removes them.

It also demonstrates MongoDB flexible schema by adding fields that are not normally in the sample dataset (for example `flexField`, `streamingAvailability`, and `criticNotes`).

## Files

- `add_demo_movies.py`: Inserts up to 5 demo movies into `sample_mflix.movies`.
- `remove_demo_movies.py`: Deletes only demo movies created by this demo.
- `.env.example`: Environment variable template.

## Setup

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create `.env` from the template:

```bash
cp .env.example .env
```

3. Confirm `.env` values:

```env
DB_NAME=sample_mflix
COLLECTION_NAME=movies
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority
```

## 1) Insert Demo Movies

```bash
python3 add_demo_movies.py
```

The script tags inserted records with:

`demoTag = "crud-flex-schema-demo-v1"`

It also checks for existing `demoMovieId` values and skips duplicates.

## 2) Pull Demo Movies in mongosh

Use this query to view only the demo records (5 or fewer):

```javascript
use sample_mflix
db.movies.find(
  { demoTag: "crud-flex-schema-demo-v1" },
  {
    _id: 0,
    demoMovieId: 1,
    title: 1,
    year: 1,
    flexField: 1,
    streamingAvailability: 1,
    criticNotes: 1
  }
).sort({ demoMovieId: 1 }).limit(5)
```

## 3) Remove Demo Movies

```bash
python3 remove_demo_movies.py
```

This script checks whether demo movies exist first.
If none exist, it prints a message and exits cleanly (no failure).
