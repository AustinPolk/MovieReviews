from typing import Callable
from imdb import Cinemagoer
import numpy as np
from spacy import Language, load
from gensim import downloader
import math
from keras import Model, Sequential, layers
from sklearn import svm

def get_movie_ids(movies: dict[str, int]) -> dict[str, str]:
    movies_by_id = {}
    ia = Cinemagoer()
    for movie, year in movies.items():
        search_results = ia.search_movie(movie)
        if year == -1:
            result = search_results[0]
        else:
            same_year = [x for x in search_results if int(x['year']) == int(year)]
            result = same_year[0]
        id = result.movieID
        movies_by_id[id] = movie
    return movies_by_id

def get_movie_plots(movie_ids: list[str]) -> dict[str, str]:
    plots_by_id = {}
    ia = Cinemagoer()
    for movie_id in movie_ids:
        for i in range(10):
            try:
                movie = ia.get_movie(movie_id)
                synopsis = movie['synopsis']
                plot = ""
                for s in synopsis:
                    plot += f"{s} "
            except:
                continue
            break
        else:
            print(f"Could not retrieve plot information for {movie_id}")
            continue
        plots_by_id[movie_id] = plot
    return plots_by_id

def get_plot_keywords(nlp: Language, movie_plot: str, adjectives: bool) -> set[str]:

    doc = nlp(movie_plot)
    word_classes = ["NOUN", "VERB"]
    if adjectives:
        word_classes.append("ADJ")

    keywords = set()
    for token in doc:
        if token.pos_ not in word_classes:
            continue
        lem = token.lemma_
        keywords.add(lem)

    return keywords

def get_plots_keywords(movie_plots: dict[str, str], adjectives: bool = False) -> dict[str, set[str]]:
    nlp = load("en_core_web_sm")
    
    keywords_by_id = {}
    for id, plot in movie_plots.items():
        keywords = get_plot_keywords(nlp, plot, adjectives)
        keywords_by_id[id] = keywords
    
    return keywords_by_id

def get_keyword_counts(movie_keywords: dict[str, str]) -> dict[str, int]:
    keyword_counts = {}
    for id, keywords in movie_keywords.items():
        for keyword in keywords:
            if keyword not in keyword_counts:
                keyword_counts[keyword] = 0
            keyword_counts[keyword] += 1
    return keyword_counts

def trim_keyword_list(keyword_counts: dict[str, int], min_occurrences: int, max_occurrences: int) -> list[str]:
    trimmed = []
    for keyword, count in keyword_counts.items():
        if count >= min_occurrences and count <= max_occurrences:
            trimmed.append(keyword)
    return trimmed

def get_movie_keyword_vector(master_keyword_list: list[str], movie_keywords: set[str], idx_by_keyword: dict[str, int]) -> np.ndarray:
    n = len(master_keyword_list)
    vec = np.zeros(n)

    for keyword in movie_keywords:
        if keyword in master_keyword_list:
            idx = idx_by_keyword[keyword]
            vec[idx] = 1
    
    return vec

def get_movie_keyword_vectors(master_keyword_list: list[str], movies_keywords: dict[str, set[str]]) -> dict[str, np.ndarray]:
    idx_by_keyword = {}
    for idx, keyword in enumerate(master_keyword_list):
        idx_by_keyword[keyword] = idx
    
    vectors_by_id = {}
    for id, keywords in movies_keywords.items():
        vec = get_movie_keyword_vector(master_keyword_list, keywords, idx_by_keyword)
        vectors_by_id[id] = vec

    return vectors_by_id

def get_word2vec_movie_vector(master_keyword_list: list[str], movie_vector: np.ndarray, embeddings) -> np.ndarray:
    n = embeddings['word'].shape[0]
    word2vec_vec = np.zeros(n)

    for idx, keyword in enumerate(master_keyword_list):
        if movie_vector[idx]:
            try:
                word_vec = embeddings[keyword]
                word2vec_vec += word_vec
            except:
                continue
    
    return word2vec_vec

def compress_vector_dimensions(vector: np.ndarray, dimensions: int, geometric: bool):
    n = vector.shape[0]
    if n % dimensions:
        print(f"{n} dimensions cannot be compressed to {dimensions}")
        return
    
    compressed = np.zeros(dimensions)
    m = n // dimensions
    
    counter = 0
    for i in range(dimensions):
        average = 1 if geometric else 0
        for j in range(m):
            elem = vector[counter]
            counter += 1
            if geometric:
                average *= elem
            else:
                average += elem
        if geometric:
            average = math.pow(average, 1 / m)
        else:
            average /= m
        compressed[i] = average

    return compressed

def get_encoder(input_size: int, latent_size: int, hidden_activation: str, latent_activation: str) -> Model:

    emid = min(64, input_size // 2)
    e1 = int(emid + 0.25 * (input_size - emid))
    e3 = int(latent_size + 0.25 * (emid - latent_size))
    encoder = Sequential([
        layers.Dense(e1, activation=hidden_activation, input_shape=(input_size,)),
        layers.Dense(emid, activation=hidden_activation),
        layers.Dense(e3, activation=hidden_activation),
        layers.Dense(latent_size, activation=latent_activation)
    ])

    encoder.compile(loss='mse', optimizer='adam')

    print(f"Encoder structure: {input_size} -> {e1} -> {emid} -> {e3} -> {latent_size}")

    return encoder

def get_movies_genres(movie_ids: list[str]) -> dict[str, list[str]]:
    genres_by_id = {}
    ia = Cinemagoer()

    for movie_id in movie_ids:
        for i in range(10):
            try:
                movie = ia.get_movie(movie_id)
                genres = movie.data['genres']
                genres_by_id[id] = genres
            except:
                continue
            break
        else:
            print(f"Could not get genre information for {movie_id}")

    return genres_by_id

def get_genres_list(genres_by_id: dict[str, list[str]]) -> list[str]:
    genres_set = set()
    for _, genres in genres_by_id.items():
        for genre in genres:
            genres_set.add(genre)
    genres_list = list(genres_set)
    return genres_list

def get_movie_genre_vector(master_genre_list: list[str], movie_genres: list[str], idx_by_genre: dict[str, int]) -> np.ndarray:
    n = len(master_genre_list)
    vec = np.zeros(n)

    for genre in movie_genres:
        if genre in master_genre_list:
            idx = idx_by_genre[genre]
            vec[idx] = 1

    return vec

def get_movies_genre_vectors(master_genre_list: list[str], movies_genres: dict[str, list[str]]) -> dict[str, np.ndarray]:
    idx_by_genre = {}
    for idx, genre in enumerate(master_genre_list):
        idx_by_genre[genre] = idx

    vectors_by_id = {}
    for id, genres in movies_genres.items():
        vec = get_movie_genre_vector(master_genre_list, genres, idx_by_genre)
        vectors_by_id[id] = vec
    
    return vectors_by_id

def get_random_features(movie_ids: list[str], dimensions: int, rand_function: Callable[[int], np.ndarray]) -> dict[str, np.ndarray]:
    vectors_by_id = {}
    for id in movie_ids:
        vec = rand_function(dimensions)
        vectors_by_id[id] = vec
    return vectors_by_id

def train_keyword_to_feature_encoder(encoder: Model, keyword_vectors: dict[str, np.ndarray], feature_vectors: dict[str, np.ndarray], epochs: int = 100) -> Model:
    n = len(next(iter(keyword_vectors)))
    input_features = []
    for i in range(n):
        this_feature = []
        for _, vector in keyword_vectors.items():
            this_feature.append(vector[i])
        this_vec = np.array(this_feature)
        input_features.append(this_vec)
    
    m = len(next(iter(feature_vectors)))
    output_features = []
    for i in range(m):
        this_feature = []
        for _, vector in feature_vectors.items():
            this_feature.append(vector[i])
        this_vec = np.array(this_feature)
        output_features.append(this_vec)

    encoder.fit(x = input_features, y = output_features, epochs = epochs)

    return encoder

class UserModel:
    def __init__(self, pos: svm.SVC, neg: svm.SVC):
        self.pos_classifier: svm.SVC = pos
        self.neg_classifier: svm.SVC = neg
        self.pos_weight: float = 1.0
        self.neg_weight: float = 1.0
        self.has_pos: bool = True
        self.has_neg: bool = True

    def fit(self, pX, pY, nX, nY):
        if not pX:
            self.has_pos = False
        if not nX:
            self.has_neg = False 
        
        if self.has_pos:
            self.pos_classifier.fit(pX, pY)
            pscore = self.pos_classifier.score(pX, pY)
            self.pos_weight = pscore

        if self.has_neg:
            self.neg_classifier.fit(nX, nY)
            nscore = self.neg_classifier.score(nX, nY)
            self.neg_weight = nscore
    
    def _sigmoid(self, x):
        return 1 / (1 + math.exp(-x))

    def predict(self, X):
        p_pred = self.pos_classifier.predict(X) if self.has_pos else 0
        n_pred = self.neg_classifier.predict(X) if self.has_neg else 0
        total = p_pred[0] * self.pos_weight + n_pred[0] * self.neg_weight
        return self._sigmoid(total)


def train_user_model(pos_classifier: svm.SVC, neg_classifier: svm.SVC, feature_vectors: dict[str, np.ndarray], user_preferences: dict[str, int]) -> UserModel:
    pos_X = []
    pos_Y = []
    neg_X = []
    neg_Y = []

    for id, preference in user_preferences.items():
        vec = feature_vectors[id]
        if preference:
            pos_X.append(vec)
            pos_Y.append(1)
        else:
            neg_X.append(vec)
            neg_Y.append(1)

    userModel = UserModel(pos_classifier, neg_classifier)
    userModel.fit(pos_X, pos_Y, neg_X, neg_Y)

    return userModel