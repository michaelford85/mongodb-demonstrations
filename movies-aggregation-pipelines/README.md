# MongoDB Aggregation Pipeline Example (Python)

This example connects to MongoDB Atlas and runs an aggregation pipeline against `sample_mflix.movies` using Python.

## Prerequisites

- Python 3.10+
- A MongoDB Atlas cluster with access to the `sample_mflix` dataset

## Setup

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Create a `.env` file in this directory with:

```env
DB_NAME=sample_mflix
COLLECTION_NAME=movies

# Your Atlas connection string (must have access to sample_mflix)
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority
```

You can copy `.env.example` and edit it:

```bash
cp .env.example .env
```

## Run

```bash
python3 main.py
```

## Aggregation Pipeline Steps

The script uses this aggregation flow in `main.py`:

1. Match movies where `genres` exists and is non-empty, and `imdb.rating > 0`.
2. Unwind `genres` so each movie appears once per genre.
3. Group by `genre + title` so titles are unique within each genre, and keep the max IMDb rating for each title.
4. Use `$setWindowFields` with `partitionBy: "$_id.genre"`, `sortBy: { "imdbRating": -1 }`, and `output.rank: { $documentNumber: {} }`.
5. Match only documents with `rank <= 3`.
6. Project only `genre`, `title`, `imdbRating`, and `rank`.
7. Sort by `genre` ascending and `rank` ascending.

## Pipeline Definition (Mongo Shell Style)

```javascript
db.movies.aggregate([
  {
    $match: {
      genres: { $exists: true, $not: { $size: 0 } },
      "imdb.rating": { $gt: 0 }
    }
  },
  { $unwind: "$genres" },
  {
    $group: {
      _id: { genre: "$genres", title: "$title" },
      imdbRating: { $max: "$imdb.rating" }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$_id.genre",
      sortBy: { imdbRating: -1 },
      output: { rank: { $documentNumber: {} } }
    }
  },
  { $match: { rank: { $lte: 3 } } },
  {
    $project: {
      _id: 0,
      genre: "$_id.genre",
      title: "$_id.title",
      imdbRating: 1,
      rank: 1
    }
  },
  { $sort: { genre: 1, rank: 1 } }
])
```

## Build This Pipeline in Atlas GUI

1. Open MongoDB Atlas and go to your cluster.
2. Click `Browse Collections`.
3. Open `sample_mflix` database and select the `movies` collection.
4. Click the `Aggregation` tab.
5. Add stages in this exact order: `$match`, `$unwind`, `$group`, `$setWindowFields`, `$match`, `$project`, `$sort`.
6. Paste each stage body from the pipeline above into its stage editor.
7. Click `Run` to preview results.
8. Optional: click `Export to Language`, choose `Python`, and compare with `main.py`.
