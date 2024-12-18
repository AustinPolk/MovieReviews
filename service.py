import pandas as pd
from sklearn.cluster import KMeans
import os
import pickle
import spacy
from accept import TokenAccepter
from encode import SparseVectorEncoding, MovieEncoding
import numpy as np
from fuzzywuzzy import fuzz
from inform import MovieInfo
import random
from autoencode import Autoencoder

# it is the chatbot's job to divine this information
class UserPreferences:
    def __init__(self):
        self.DescribedPlots: list[str] = None
        self.Directors: list[str] = None
        self.Actors: list[str] = None
        self.KnownLikedTitles: list[str] = None
        self.KnownLikedMovies: list[int] = None
        self.Genres: list[str] = None
        self.MoviesBefore: int = None
        self.MoviesAfter: int = None
        self.AllowAmericanOrigin: bool = None
        self.AllowBollywoordOrigin: bool = None
        self.AllowOtherOrigin: bool = None

class MovieRecommendation:
    def __init__(self, movie: MovieInfo):
        self.RecommendedMovie: MovieInfo = movie          # information for the actual movie being recommended 
        self.SimilarThemesToDescribed: list[str] = []     # list of user-provided descriptions that it has similar themes to 
        self.SimilarThemesToMovies: list[str] = []        # list of known liked movie titles that it has similar themes to
        self.SimilarGenresToMovies: list[str] = []        # list of known liked movie titles that it has similar genres to
        self.SimilarActorsToMovies: list[str] = []        # list of known liked movie titles that it has a similar cast to
        self.ExpressedLikeDirectors: list[str] = []       # list of director(s) for this movie that the user likes
        self.ExpressedLikeActors: list[str] = []          # list of actors in this movie that the user likes
        self.ExpressedLikeGenres: list[str] = []          # list of genres for this movie that the user likes
        self.WithinDesiredTimePeriod: bool = False        # does the movie fall within the desired time period
        self.HasDesiredOrigin: bool = False               # does the movie have the right origin
    # return a recommendation score based on the volume of criteria matching the user preferences
    def score(self):
        score = 0
        if self.SimilarThemesToDescribed:
            score += (1 + 0.1 * (len(self.SimilarThemesToDescribed) - 1))
        if self.SimilarThemesToMovies:
            score += (1 + 0.1 * (len(self.SimilarThemesToMovies) - 1))
        if self.SimilarGenresToMovies:
            score += (1 + 0.1 * (len(self.SimilarGenresToMovies) - 1))
        if self.SimilarActorsToMovies:
            score += (1 + 0.1 * (len(self.SimilarActorsToMovies) - 1))
        if self.ExpressedLikeDirectors:
            score += (1 + 0.1 * (len(self.ExpressedLikeDirectors) - 1))
        if self.ExpressedLikeActors:
            score += (1 + 0.1 * (len(self.ExpressedLikeActors) - 1))
        if self.ExpressedLikeGenres:
            score += (1 + 0.1 * (len(self.ExpressedLikeGenres) - 1))
        if self.WithinDesiredTimePeriod:
            score += 1
        if self.HasDesiredOrigin:
            score += 1
        return score
    
    def explain(self, bullet_list: bool, return_list: bool = False):
        exp_strs = [f'\"{self.RecommendedMovie.describe(True)}\" was recommended for the following reasons: ']
        if self.SimilarThemesToDescribed:
            for described in self.SimilarThemesToDescribed:
                exp_str = f'It has similar themes to your description of \"{described}\"'
                exp_strs.append(exp_str)
        if self.SimilarThemesToMovies:
            for title in self.SimilarThemesToMovies:
                exp_str = f'It has similar themes to the movie {title}'
                exp_strs.append(exp_str)
        if self.SimilarGenresToMovies:
            for title in self.SimilarGenresToMovies:
                exp_str = f'It is in the same genre as the movie {title}'
                exp_strs.append(exp_str)
        if self.SimilarActorsToMovies:
            for title in self.SimilarActorsToMovies:
                exp_str = f'It has some of the same cast members as the movie {title}'
                exp_strs.append(exp_str)
        if self.ExpressedLikeDirectors:
            for name in self.ExpressedLikeDirectors:
                exp_str = f'It is directed by {name}'
                exp_strs.append(exp_str)
        if self.ExpressedLikeActors:
            for name in self.ExpressedLikeActors:
                exp_str = f'It stars {name}'
                exp_strs.append(exp_str)
        if self.ExpressedLikeGenres:
            for genre in self.ExpressedLikeGenres:
                exp_str = f'It is in the {genre} genre'
                exp_strs.append(exp_str)
        if self.WithinDesiredTimePeriod:
            exp_str = 'It was released in the desired time frame'
            exp_strs.append(exp_str)
        if self.HasDesiredOrigin:
            exp_str = 'It has the desired regional origin'
            exp_strs.append(exp_str)

        if len(exp_strs) == 1:
            exp_str = 'I\'m not really sure'
            exp_strs.append(exp_str)

        if return_list:
            return exp_strs

        explanation = exp_strs[0]
        if bullet_list:
            for exp in exp_strs[1:]:
                explanation += f'\n\t- {exp}'
            explanation += '\n'
        else:
            for exp in exp_strs[1:]:
                explanation += f'{exp}, and'
            explanation = explanation[:-5]  # remove trailing and
        return explanation

class MovieService:
    def __init__(self):
        self.MovieInfo: dict[int, MovieInfo] = {}
        self.MovieEncodings: dict[int, MovieEncoding] = {}
        self.ClusterModel: KMeans = None
        self.Recommendations: dict[int, MovieRecommendation] = {}
        self.Autoencoder: Autoencoder = None
        self.load_setup_data()
        self.use_autoencoder(loss_threshold=0.0002)

    def load_setup_data(self):
        data_folder = "data"
        movie_info_bin = os.path.join(data_folder, "movie_info.bin")
        cluster_model_bin = os.path.join(data_folder, "cluster_model.bin")
        movie_encodings_bin = os.path.join(data_folder, "movie_encodings.bin")

        movieInfo = pd.read_pickle(movie_info_bin)
        ids = list(movieInfo['Id'].values)
        movieInfos = list(movieInfo['Movie'].values)
        self.MovieInfo = {id: movie_info for id, movie_info in zip(ids, movieInfos)}

        movieEncoding = pd.read_pickle(movie_encodings_bin)
        ids = list(movieEncoding['Id'].values)
        movieEncodings = list(movieEncoding['MovieEncoding'].values)
        self.MovieEncodings = {id: movie_encoding for id, movie_encoding in zip(ids, movieEncodings)}

        with open(cluster_model_bin, 'rb') as cluster_model_file:
            self.ClusterModel = pickle.load(cluster_model_file)

    def use_autoencoder(self, denormalize: bool = False, loss_threshold: float = 0.01):
        for i in range(2, 32):
            print(f"Testing {i} dimensions")
            autoencoder = Autoencoder(len(self.ClusterModel.cluster_centers_), 64, i, activation='relu')
            loss = autoencoder.train_on_movie_encodings(self.MovieEncodings, denormalize)
            print(f"Loss for {i} dimensions: {loss}")
            if loss < loss_threshold:
                print(f"Autoencoder using {i} dimensions")
                self.Autoencoder = autoencoder
                return
        else:
            print(f"Loss threshold too low, raising to {loss_threshold * 1.01} from {loss_threshold}")
            self.use_autoencoder(denormalize, loss_threshold * 1.01)

    def encode_plot_theme_query(self, plot_query: str):
        language = spacy.load("en_core_web_lg")
        tok_accepter = TokenAccepter()

        query_encoding = SparseVectorEncoding()

        tokenized = language(plot_query)
        for token in tokenized:
            if not tok_accepter.accept(token):
                continue
            dim = int(self.ClusterModel.predict(np.array([token.vector]))[0])
            query_encoding[dim] += 1
        query_encoding.normalize()

        return query_encoding
    
    def get_movie_info_by_id(self, id: int):
        return self.MovieInfo[id]

    def query_movies_by_title(self, title: str, top_n: int = 10):
        ids = list(self.MovieInfo.keys())
        similarities = {}
        for id, movieInfo in self.MovieInfo.items():
            if not movieInfo.Title:
                similarities[id] = 0
            else:
                similarities[id] = fuzz.ratio(title.lower(), movieInfo.Title.lower())
        sorted_ids = sorted(ids, key = lambda x: similarities[x], reverse=True)[:top_n]
        return [self.MovieInfo[x] for x in sorted_ids]

    def query_movies_by_director(self, director: str, from_ids: list[str]):
        director_names = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'director'] for id in from_ids}
        ids = []
        for id in director_names:
            for director_name in director_names[id]:
                # use partial ratio for directors in case only the last name is specified (e.g. Tarantino)
                ratio = fuzz.partial_ratio(director_name, director)
                if ratio > 90:
                    ids.append(id)
                    break
        return ids

    def query_movies_by_actor(self, actor: str, from_ids: list[str]):
        actor_names = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'cast'] for id in from_ids}
        ids = []
        for id in actor_names:
            for actor_name in actor_names[id]:
                ratio = fuzz.ratio(actor_name, actor)
                if ratio > 90:
                    ids.append(id)
                    break
        return ids

    def query_movies_by_genre(self, genre: str, from_ids: list[str]):
        genres = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'genre'] for id in from_ids}
        ids = []
        for id in genres:
            for genre_name in genres[id]:
                ratio = fuzz.ratio(genre_name, genre)
                if ratio > 95:
                    ids.append(id)
                    break
        return ids

    def query_movies_with_similar_plot_themes(self, similar_to: str|int, from_ids: list[str], similarity_threshold: float, cosine: bool = True):
        if similar_to in self.MovieEncodings: # it's an id
            similar_encoding = self.MovieEncodings[similar_to].PlotEncoding
        else: # it's a plot string to encode
            similar_encoding = self.encode_plot_theme_query(similar_to)
        if self.Autoencoder:
            auto_encoded = self.Autoencoder(encoding)

        plot_encodings = {id: self.MovieEncodings[id].PlotEncoding for id in from_ids}            

        similar_ids = []
        for id, encoding in plot_encodings.items():
            if self.Autoencoder:
                auto_similar = self.Autoencoder(similar_encoding)
                distance = np.linalg.norm(auto_encoded - auto_similar)
                similarity = 1 / (distance + 1)
            elif cosine:
                similarity = encoding.normed_cosine_similarity(similar_encoding)
            else: # number of similar themes, regardless of intensity, over number of themes in the similar encoding
                these_themes = set(similar_encoding.Dimensions.keys())
                those_themes = set(encoding.Dimensions.keys())
                similar_themes = len(these_themes & those_themes)
                similarity = similar_themes / len(these_themes)
            if similarity >= similarity_threshold:
                similar_ids.append(id)
        
        return similar_ids

    def query_movies_with_similar_cast(self, similar_to: str|int, from_ids: list[str], similarity_threshold: float):
        all_cast_members = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'CAST'] for id in from_ids}
        if similar_to in self.MovieEncodings: # id for a movie
            cast_members = all_cast_members[similar_to]
        else:
            cast_members = [member.strip() for member in similar_to.split(',')]
        ideal_matches = len(cast_members)
        if not ideal_matches:
            return from_ids

        ids = []
        for id, cast in all_cast_members.items():
            matches = 0
            for desired_member in cast_members:
                for member in cast:
                    if fuzz.ratio(desired_member.lower(), member.lower()) > 90:
                        matches += 1
            similarity = matches / ideal_matches
            if similarity > similarity_threshold:
                ids.append(id)
        
        return ids

    def query_movies_with_similar_genre(self, similar_to: str|int, from_ids: list[str], similarity_threshold: float):
        all_genres = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'GENRE'] for id in from_ids}
        if similar_to in self.MovieEncodings: # id for a movie
            movie_genres = all_genres[similar_to]
        else:
            movie_genres = [member.strip() for member in similar_to.split(',')]
        ideal_matches = len(movie_genres)
        if not ideal_matches:
            return from_ids

        ids = []
        for id, genres in all_genres.items():
            matches = 0
            for desired_genre in movie_genres:
                for genre in genres:
                    if fuzz.ratio(desired_genre.lower(), genre.lower()) > 90:
                        matches += 1
            similarity = matches / ideal_matches
            if similarity > similarity_threshold:
                ids.append(id)
        
        return ids

    def query_movies_before(self, year: int, from_ids: list[str]):
        return [id for id in from_ids if int(self.MovieInfo[id].Year) < year]

    def query_movies_after_or_on(self, year: int, from_ids: list[str]):
        return [id for id in from_ids if int(self.MovieInfo[id].Year) >= year]
    
    def query_american_movies(self, from_ids: list[str]):
        return [id for id in from_ids if self.MovieInfo[id].Origin.lower() == 'american']
    
    def query_bollywood_movies(self, from_ids: list[str]):
        return [id for id in from_ids if self.MovieInfo[id].Origin.lower() == 'bollywood']

    def query_other_foreign_movies(self, from_ids: list[str]):
        return [id for id in from_ids if self.MovieInfo[id].Origin.lower() != 'bollywood' and self.MovieInfo[id].Origin.lower() != 'american']

    # works more like a filter, does not rank
    def query_from_user_preferences(self, user_preferences: UserPreferences, similarity_threshold: float = 0.6, union_query: bool = True, top_n: int = 10):
        remaining_ids = set(self.MovieEncodings.keys())
        union = set()

        if user_preferences.DescribedPlots:
            all_similar = set()
            for described in user_preferences.DescribedPlots:
                similar_to_described = self.query_movies_with_similar_plot_themes(described, list(remaining_ids), similarity_threshold)
                all_similar |= set(similar_to_described)

            if union_query:
                union |= all_similar
            else:
                remaining_ids &= all_similar

        if user_preferences.KnownLikedMovies:
            all_similar = set()
            for movie_id in user_preferences.KnownLikedMovies:
                with_similar_themes = self.query_movies_with_similar_plot_themes(movie_id, list(remaining_ids), similarity_threshold)
                with_similar_cast = self.query_movies_with_similar_cast(movie_id, list(remaining_ids), similarity_threshold)
                with_similar_genre = self.query_movies_with_similar_genre(movie_id, list(remaining_ids), similarity_threshold)
                similar_movies = list(set(with_similar_themes) | set(with_similar_cast) | set(with_similar_genre))
                all_similar |= set(similar_movies)

            if union_query:
                union |= all_similar
            else:
                remaining_ids &= all_similar
        
        if user_preferences.Directors:
            all_by_director = set()
            for director in user_preferences.Directors:
                by_director = self.query_movies_by_director(director.lower(), list(remaining_ids))
                all_by_director |= set(by_director)

            if union_query:
                union |= all_by_director
            else:
                remaining_ids &= all_by_director
        
        if user_preferences.Actors:
            all_with_actor = set()
            for actor in user_preferences.Actors:
                with_actor = self.query_movies_by_actor(actor.lower(), list(remaining_ids))
                all_with_actor |= set(with_actor)
            
            if union_query:
                union |= all_with_actor
            else:
                remaining_ids &= all_with_actor
        
        if user_preferences.Genres:
            all_in_genre = set()
            for genre in user_preferences.Genres:
                in_genre = self.query_movies_by_genre(genre.lower(), list(remaining_ids))
                all_in_genre |= set(in_genre)

            if union_query:
                union |= all_in_genre
            else:
                remaining_ids &= all_in_genre
                  
        if user_preferences.MoviesAfter:
            movies_after = self.query_movies_after_or_on(user_preferences.MoviesAfter, list(remaining_ids))
            movies_after = set(movies_after)

            # this must be applied as an intersection
            if union_query:
                union &= movies_after
            else:
                remaining_ids &= movies_after

        if user_preferences.MoviesBefore:
            movies_before = self.query_movies_before(user_preferences.MoviesBefore, list(remaining_ids))
            movies_before = set(movies_before)

            # this must be applied as an intersection
            if union_query:
                union &= movies_before
            else:
                remaining_ids &= movies_before

        # assemble the list of movies from the allowed origins
        from_allowed_origins = set()

        if user_preferences.AllowAmericanOrigin:
            american = self.query_american_movies(list(remaining_ids))
            american = set(american)
            from_allowed_origins |= american

        if user_preferences.AllowBollywoordOrigin:
            bollywood = self.query_bollywood_movies(list(remaining_ids))
            bollywood = set(bollywood)
            from_allowed_origins |= bollywood

        if user_preferences.AllowOtherOrigin:
            other_origin = self.query_other_foreign_movies(list(remaining_ids))
            other_origin = set(other_origin)
            from_allowed_origins |= other_origin

        # only filter if it wouldn't automatically delete the whole query
        if from_allowed_origins:
            # must be applied as an intersection
            if union_query:
                union &= from_allowed_origins
            else:
                remaining_ids &= from_allowed_origins

        if union_query:
            movie_ids = list(union - set(user_preferences.KnownLikedMovies))
        else:
            movie_ids = list(remaining_ids - set(user_preferences.KnownLikedMovies))
        
        queried_movies = [self.MovieInfo[x] for x in movie_ids]

        return queried_movies[:top_n]

    def recommend_movies_by_director(self, director: str):
        director_names = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'director'] for id in self.Recommendations}
        for id in director_names:
            for director_name in director_names[id]:
                # use partial ratio for directors in case only the last name is specified (e.g. Tarantino)
                ratio = fuzz.partial_ratio(director_name.lower(), director)
                if ratio > 90:
                    self.Recommendations[id].ExpressedLikeDirectors.append(director)
                    break

    def recommend_movies_by_actor(self, actor: str):
        actor_names = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'cast'] for id in self.Recommendations}
        for id in actor_names:
            for actor_name in actor_names[id]:
                ratio = fuzz.ratio(actor_name.lower(), actor)
                if ratio > 90:
                    self.Recommendations[id].ExpressedLikeActors.append(actor)
                    break

    def recommend_movies_by_genre(self, genre: str):
        genres = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'genre'] for id in self.Recommendations}
        for id in genres:
            for genre_name in genres[id]:
                ratio = fuzz.ratio(genre_name.lower(), genre)
                if ratio > 95:
                    self.Recommendations[id].ExpressedLikeGenres.append(genre)
                    break

    def recommend_movies_with_similar_plot_themes(self, similar_to: str|int, similarity_threshold: float, cosine: bool = True):
        described = False
        if similar_to in self.MovieEncodings: # it's an id
            similar_encoding = self.MovieEncodings[similar_to].PlotEncoding
        else: # it's a plot string to encode
            similar_encoding = self.encode_plot_theme_query(similar_to)
            described = True

        plot_encodings = {id: self.MovieEncodings[id].PlotEncoding for id in self.Recommendations}

        for id, encoding in plot_encodings.items():
            if cosine:
                similarity = encoding.normed_cosine_similarity(similar_encoding)
            else: # number of similar themes, regardless of intensity, over number of themes in the similar encoding
                these_themes = set(similar_encoding.Dimensions.keys())
                those_themes = set(encoding.Dimensions.keys())
                similar_themes = len(these_themes & those_themes)
                similarity = similar_themes / len(these_themes)
            if similarity >= similarity_threshold:
                if described:
                    self.Recommendations[id].SimilarThemesToDescribed.append(similar_to)
                else:
                    title = self.MovieInfo[similar_to].describe(True)
                    self.Recommendations[id].SimilarThemesToMovies.append(title)

    def recommend_movies_with_similar_cast(self, similar_to: str|int, similarity_threshold: float):
        all_cast_members = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'CAST'] for id in self.Recommendations}
        # for now assume that it always is an id
        if similar_to in self.MovieEncodings: # id for a movie
            cast_members = all_cast_members[similar_to]
        #else:
        #    cast_members = [member.strip() for member in similar_to.split(',')]
        ideal_matches = len(cast_members)
        if not ideal_matches:
            return

        for id, cast in all_cast_members.items():
            matches = 0
            for desired_member in cast_members:
                for member in cast:
                    if fuzz.ratio(desired_member, member) > 90:
                        matches += 1
            similarity = matches / ideal_matches
            if similarity > similarity_threshold:
                title = self.MovieInfo[similar_to].describe(True)
                self.Recommendations[id].SimilarActorsToMovies.append(title)

    def recommend_movies_with_similar_genre(self, similar_to: str|int, similarity_threshold: float):
        all_genres = {id: [ent.EntityName for ent in self.MovieEncodings[id].EntityEncodings if ent.EntityLabel.lower() == 'GENRE'] for id in self.Recommendations}
        # for now assume that it is always an id
        if similar_to in self.MovieEncodings: # id for a movie
            movie_genres = all_genres[similar_to]
        #else:
        #    movie_genres = [member.strip() for member in similar_to.split(',')]
        ideal_matches = len(movie_genres)
        if not ideal_matches:
            return

        for id, genres in all_genres.items():
            matches = 0
            for desired_genre in movie_genres:
                for genre in genres:
                    if fuzz.ratio(desired_genre, genre) > 90:
                        matches += 1
            similarity = matches / ideal_matches
            if similarity > similarity_threshold:
                title = self.MovieInfo[similar_to].describe(True)
                self.Recommendations[id].SimilarGenresToMovies.append(title)

    def recommend_movies_before(self, year: int):
        for _, recommendation in self.Recommendations.items():
            if recommendation.RecommendedMovie.Year < year:
                recommendation.WithinDesiredTimePeriod = True

    def recommend_movies_after_or_on(self, year: int):
        for _, recommendation in self.Recommendations.items():
            if recommendation.RecommendedMovie.Year >= year:
                recommendation.WithinDesiredTimePeriod = True
    
    def recommend_american_movies(self):
        for _, recommendation in self.Recommendations.items():
            if recommendation.RecommendedMovie.Origin.lower() == 'american':
                recommendation.HasDesiredOrigin = True
    
    def recommend_bollywood_movies(self):
        for _, recommendation in self.Recommendations.items():
            if recommendation.RecommendedMovie.Origin.lower() == 'bollywood':
                recommendation.HasDesiredOrigin = True

    def recommend_other_foreign_movies(self):
        for _, recommendation in self.Recommendations.items():
            if recommendation.RecommendedMovie.Origin.lower() != 'american' and recommendation.RecommendedMovie.Origin.lower() != 'bollywood':
                recommendation.HasDesiredOrigin = True

    # does not filter, but will rank
    def recommend_from_user_preferences(self, user_preferences: UserPreferences, top_n: int = 10, mixed_results: bool = False, similarity_threshold: float = 0.6):
        # check if there are titles the user likes which haven't been correlated to a movie Id
        if user_preferences.KnownLikedTitles and not user_preferences.KnownLikedMovies:
            user_preferences.KnownLikedMovies = []
            for title in user_preferences.KnownLikedTitles:
                likely_movie = self.query_movies_by_title(title, top_n=1)[0]
                likely_id = likely_movie.Id
                user_preferences.KnownLikedMovies.append(likely_id)
        
        ids = list(self.MovieEncodings.keys())
        self.Recommendations = {id: MovieRecommendation(self.MovieInfo[id]) for id in ids}

        if user_preferences.DescribedPlots:
            for described in user_preferences.DescribedPlots:
                self.recommend_movies_with_similar_plot_themes(described, similarity_threshold)
        if user_preferences.KnownLikedMovies:
            for movie_id in user_preferences.KnownLikedMovies:
                self.recommend_movies_with_similar_plot_themes(movie_id, similarity_threshold)
                #self.recommend_movies_with_similar_cast(movie_id, similarity_threshold)
                #self.recommend_movies_with_similar_genre(movie_id, similarity_threshold)
        if user_preferences.Directors:
            for director in user_preferences.Directors:
                self.recommend_movies_by_director(director.lower())
        if user_preferences.Actors:
            for actor in user_preferences.Actors:
                self.recommend_movies_by_actor(actor.lower())
        if user_preferences.Genres:
            for genre in user_preferences.Genres:
                self.recommend_movies_by_genre(genre.lower())
        if user_preferences.MoviesAfter:
            self.recommend_movies_after_or_on(user_preferences.MoviesAfter)
        if user_preferences.MoviesBefore:
            self.recommend_movies_before(user_preferences.MoviesBefore)
        if user_preferences.AllowAmericanOrigin:
            self.recommend_american_movies()
        if user_preferences.AllowBollywoordOrigin:
            self.recommend_bollywood_movies()
        if user_preferences.AllowOtherOrigin:
            self.recommend_other_foreign_movies()

        if user_preferences.KnownLikedMovies:
            movie_ids = list(set(self.Recommendations.keys()) - set(user_preferences.KnownLikedMovies))
        else:
            movie_ids = list(self.Recommendations.keys())
        random.shuffle(movie_ids)

        # oversample the recommended ids in case the results should be mixed
        recommended_ids = sorted(movie_ids, key = lambda x: self.Recommendations[x].score(), reverse=True)[:2 * top_n]

        # if mixed_results, shuffle the oversampled recommendations
        if mixed_results:
            random.shuffle(recommended_ids)
        # get the correct number of recommendations
        recommended_ids = recommended_ids[:top_n]

        recommendations = [self.Recommendations[x] for x in recommended_ids]
        return recommendations