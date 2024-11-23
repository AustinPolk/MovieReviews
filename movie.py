import pickle
import pandas as pd
import spacy
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import numpy as np
from fuzzywuzzy import fuzz
import os

class SparseVectorEncoding:
    def __init__(self):
        self.Dimensions: dict[int, float] = {}  # actual values in the vector, indexed by dimension
        self.Norm: float = None                 # magnitude of the vector, used in normalization/cosine similarity
    def __getitem__(self, index: int):
        if index not in self.Dimensions:    # any value not recorded is assumed 0 in the vector
            return 0
        return self.Dimensions[index]
    def __setitem__(self, index: int, value: float):
        self.Dimensions[index] = value
    def normalize(self):
        self.Norm = sum(A * A for A in self.Dimensions.values()) ** 0.5
        for dim in self.Dimensions:
            self[dim] /= self.Norm
    def normed_cosine_similarity(self, other):
        if not self.Norm:
            self.normalize()
        if not other.Norm:
            other.normalize()
        common_dims = set(self.Dimensions.keys()) & set(other.Dimensions.keys())
        similarity = 0
        for dim in common_dims:
            similarity += self[dim] * other[dim]
        return similarity

# for now just relies on string similarity, in the future could be name vectors
class EntityEncoding:
    def __init__(self, entity: str, label: str):
        self.EntityName: str = entity.lower()
        self.EntityLabel: str = label.lower()
    def similarity(self, other):
        if self.EntityLabel != other.EntityLabel:
            return 0
        return fuzz.ratio(self.EntityName, other.EntityName) / 100

class MovieEncoding:
    def __init__(self):
        self.PlotEncoding: SparseVectorEncoding = SparseVectorEncoding()
        self.EntityEncodings: list[EntityEncoding] = []
    def add_entity(self, entity_encoding: EntityEncoding):
        max_similarity = max(entity_encoding.similarity(x) for x in self.EntityEncodings)
        if max_similarity < 0.95:    # don't add if it is too similar, it is likely a repeat
            self.EntityEncodings.append(entity_encoding)
    def estimate_entity_matches(self, other):
        these_entities = list(self.EntityEncodings)
        those_entities = list(other.EntityEncodings)
        matches = 0

        # attempt to make a 1 to 1 matching from these entities to those entities
        while these_entities and those_entities:
            ent = these_entities.pop()
            best_match = None
            best_similarity = 0
            for other_ent in those_entities:
                similarity = ent.similarity(other_ent)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = other_ent
            if best_similarity > 0.85:  # threshold for what counts as a match
                matches += 1
                those_entities.remove(best_match)
        
        return matches
    def similarity(self, other):
        max_matches = min(len(self.EntityEncodings), len(other.EntityEncodings)) + 1    # +1 just to make the resultant similarity a little smaller
        ent_sim_score = self.estimate_entity_matches(other) / max_matches
        plot_sim_score = self.PlotEncoding.normed_cosine_similarity(other.PlotEncoding)
        return 0.65 * plot_sim_score + 0.35 * ent_sim_score     # give the plot score a higher weight, but still let the entity score have some say

class MovieInfo:
    def __init__(self):
        self.Title: str = None                      # title of the movie
        self.Plot: str = None                       # plot of the movie
        self.Year: int = None                       # year that the movie was released
        self.Director: list[str] = None             # director of the movie, if known (otherwise None)
        self.Origin: str = None                     # "origin" of the movie (e.g. American, Tamil)
        self.Cast: list[str] = None                 # list of cast members in the movie, if known (otherwise None)
        self.Id: int = None                         # unique number to refer to this particular movie
        self.Genre: list[str] = None                # genres attributed to the movie, if known (otherwise None)
    def set(self, attr: str, value: str):
        # replace an actual missing value with empty string
        if pd.isna(value):
            value = ""

        # remove any quotes or whitespace from the beginning and end of the string
        strip = lambda s: s.strip("\"\'\n\r ")
        value = strip(value)
        
        # remove the pipe character if present, as it has a special purpose in the string representation of the movie
        value = value.replace("|", " ")
        
        # if the value is unknown, set it to none
        none_if_unknown = lambda s: None if not s or s.isspace() or s.lower() == 'unknown' else s
        value = none_if_unknown(value)

        if attr == 'Title':
            self.Title = value
        elif attr == 'Plot':
            self.Plot = value
        elif attr == 'Year':
            self.Year = int(value)
        elif attr == 'Director':
            if not value:
                self.Director = value
            self.Director = []
            # remove quotes from nicknames
            dequote = lambda x: x.replace('\'', '').replace('\"', '')
            list_elements = [dequote(strip(director)) for director in value.split(',')]
            for element in list_elements:
                # if this element looks like "and John Smith", make it "John Smith"
                no_and = element[4:] if element.startswith('and ') else element
                # split a list separated by an 'and' instead of a','
                for sub_element in element.split(' and '):
                    self.Director.append(sub_element)
        elif attr == 'Origin':
            self.Origin = value
        elif attr == 'Cast':
            if not value:
                self.Cast = value
            else:
                self.Cast = [strip(member) for member in value.split(',')]
        elif attr == 'Genre':
            if not value:
                self.Genre = value
            self.Genre = []
            # split the genre into a list of genres
            list_elements = [strip(genre) for genre in value.split(',')]
            # try to get as granular of data as possible on the genre
            for element in list_elements:
                self.Genre.append(element)
                # separate genres like "romantic comedy" into "romantic" and "comedy"
                for sub_element in element.split():
                    self.Genre.append(sub_element)
                    # separate genres like "drama/thriller" into "drama" and "thriller"
                    for sub_sub_element in sub_element.split('-/'):
                        self.Genre.append(sub_sub_element)
        elif attr == 'Id':
            self.Id = int(value)
        else:
            raise Exception() 
    def describe(self, short: bool):
        desc = f"{self.Title} ({self.Year})"
        if short:
            return desc
        if self.Origin:
            desc = f"{desc[:-1]}, {self.Origin})"
        if self.Director:
            desc = f"{desc}, directed by "
            if len(self.Director) == 1:
                desc += self.Director[0]
            else:
                for name in self.Director[:-1]:
                    desc += f"{name}, "
                desc += f"and {self.Director[-1]}"
        if self.Cast:
            desc = f"{desc}, starring "
            if len(self.Cast) == 1:
                desc += self.Cast[0]
            else:
                for name in self.Cast[:-1]:
                    desc += f"{name}, "
                desc += f"and {self.Cast[-1]}"
        return desc

class TokenizedPlot:
    def __init__(self):
        self.Tokens: list[(str, str)] = []
        self.Vectors: dict[(str, str), np.ndarray] = {}
        self.Entities: list[(str, str)] = []

class TokenAccepter:
    def __init__(self):
        pass
    def accept(self, token):
        if token.pos_ not in ["NOUN", "VERB", "ADJ", "ADV"]:    # only accept words in an open class
            return False
        if not token.has_vector:    # only accept words with available vector embeddings
            return False
        return True
    
class EntityAccepter:
    def __init__(self):
        pass
    def accept(self, entity):
        if entity.label_ in ["TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"]:    # do not accept these entity types, they aren't very useful
            return False
        return True

class MovieServiceSetup:
    def __init__(self):
        self.setup()

    # source is the csv file containing movie info, 
    # sink is a binary file containing formatted movie info
    def load_all_movie_info(self, source: str, sink: str):
        # this step has already been completed
        if os.path.exists(sink):
            print("Movies already loaded")
            return

        source_frame = pd.read_csv(source)
        movie_infos = []
        for idx, row in source_frame.iterrows():
            try:
                movie = MovieInfo()
                movie.set("Title", row['Title'])
                movie.set("Plot", row['Plot'])
                movie.set("Year", str(row['Release Year']))
                movie.set("Director", row['Director'])
                movie.set("Origin", row['Origin/Ethnicity'])
                movie.set("Cast", row['Cast'])
                movie.set("Genre", row['Genre'])
                movie.Id = idx

                movie_infos.append((movie.Id, movie))
                print(movie.Id, movie.describe(False))
            except:
                continue
        sink_frame = pd.DataFrame(movie_infos, columns=['Id', 'Movie'])
        sink_frame.to_pickle(sink)

    # source is a binary file containing formatted movie info, 
    # sink is a binary file containing tokenized plots, 
    # vector_sink is a binary file of word vector embeddings
    def tokenize_all_plots_plus_vectors(self, source: str, sink: str, vector_sink: str, start_idx: int, end_idx: int):
        # this step has already been completed
        if os.path.exists(sink) and os.path.exists(vector_sink):
            print(f"Plots {start_idx} to {end_idx-1} alraedy tokenized")
            return

        language = spacy.load("en_core_web_lg")
        source_frame = pd.read_pickle(source)
        tokenized_plots = []
        word_vectors = {}

        tok_accepter = TokenAccepter()
        ent_accepter = EntityAccepter()
        for idx, row in source_frame.iterrows():
            # note that if end_idx < start_idx, it will go from start_idx all the way through (this is intended)
            if idx < start_idx:
                continue
            elif idx == end_idx:
                break
            
            try:
                movie = row['Movie']
                plot = movie.Plot
                tokenized_plot = TokenizedPlot()

                tokenized = language(plot)
                for token in tokenized:
                    if not tok_accepter.accept(token):
                        continue
                    if (token.lemma_, token.pos_) not in word_vectors:
                        word_vectors[(token.lemma_, token.pos_)] = token.vector
                        tokenized_plot.Vectors[(token.lemma_, token.pos_)] = token.vector
                    tokenized_plot.Tokens.append((token.lemma_, token.pos_))
                for entity in tokenized.ents:
                    if not ent_accepter.accept(entity):
                        continue
                    tokenized_plot.Entities.append((entity.text, entity.label_))
                
                # add special entities pertaining to the movie's production
                if movie.Director:
                    tokenized_plot.Entities.append((movie.Director, "DIRECTOR"))
                if movie.Cast:
                    for member in movie.Cast:
                        tokenized_plot.Entities.append((member, "CAST"))
                if movie.Genre:
                    for genre in movie.Genre:
                        tokenized_plot.Entities.append((genre, "GENRE"))
                if movie.Origin:
                    tokenized_plot.Entities.append((movie.Origin, "ORIGIN"))
                
                print(movie.Id, movie.describe(False), f"({len(tokenized_plot.Tokens)}, {len(tokenized_plot.Entities)})")
                tokenized_plots.append((movie.Id, tokenized_plot))
            except:
                continue

        just_vectors = list(word_vectors.values())
        with open(vector_sink, "wb+") as vector_file:
            pickle.dump(just_vectors, vector_file)

        sink_frame = pd.DataFrame(tokenized_plots, columns=['Id', 'TokenizedPlot'])
        sink_frame.to_pickle(sink)

    # sources is a list of binary files containing tokenized plots
    # vector sources is a list of binary files containing word vector embeddings
    # sink is the combined file containing all tokenized plots
    # vector_sink is the combined file containing all word vector embeddings
    def combine_tokenized_results(self, sources: list[str], vector_sources: list[str], sink: str, vector_sink: str):
        if not os.path.exists(sink):
            print("Combining tokenized plots")
            all_tokenized = pd.read_pickle(sources[0])
            for source in sources[1:]:
                this_tokenized = pd.read_pickle(source)
                all_tokenized = pd.concat([all_tokenized, this_tokenized], ignore_index=True)
            all_tokenized.to_pickle(sink)
        else:
            print("Tokenized plots already combined")

        if not os.path.exists(vector_sink):
            print("Combining all known word vectors")
            all_vectors = []
            for vector_source in vector_sources:
                with open(vector_source, "rb") as vector_file:
                    these_vectors = pickle.load(vector_file)
                    all_vectors.extend(these_vectors)
            all_vectors = list(set(all_vectors))
            all_vectors = np.array(all_vectors)
            with open(vector_sink, "wb+") as vector_file:
                pickle.dump(all_vectors, vector_file)
        else:
            print("Word vectors already combined")

    # source is a binary file containing word vector embeddings, 
    # sink is a binary file containing a clustering model,
    # score_sink is a binary file containing scores for different cluster sizes
    def train_cluster_model_on_vectors(self, source: str, sink: str, score_sink:str, min_clusters: int, max_clusters: int, cluster_step: int = 500):
        if os.path.exists(sink) and os.path.exists(score_sink):
            print("Clustering model already chosen")
            return
        
        with open(source, "rb") as vector_file:
            word_vectors = pickle.load(vector_file)

        print(f"Performing clustering on {len(word_vectors)} word vectors")
        
        best_cluster_model = None
        best_score = -1
        all_scores = {}

        # do max clusters + 1 so that max_clusters will get tested and not skipped
        for n_clusters in range(min_clusters, max_clusters + 1, cluster_step):
            cluster_model = KMeans(n_clusters=n_clusters, random_state=26)
            cluster_model.fit(word_vectors)
            score = silhouette_score(word_vectors, cluster_model.labels_)
            print(f"Silhouette score for {n_clusters} clusters: {score}")

            if score > best_score:
                best_score = score
                best_cluster_model = cluster_model

            all_scores[n_clusters] = score

        print(f"{len(best_cluster_model.cluster_centers_)} clusters achieved the highest silhouette score ({best_score})")

        with open(sink, "wb+") as cluster_file:
            pickle.dump(best_cluster_model, cluster_file)
        
        with open(score_sink, "wb+") as score_file:
            pickle.dump(all_scores, score_file)

    # source is a binary file containing tokenized plots
    # cluster_source is a binary file containing a clustering model
    # sink is a binary file containing the final encodings
    def encode_all_movies(self, source: str, vector_source: str, cluster_source: str, sink: str):
        if os.path.exists(sink):
            print("All movies already encoded")
            return
        
        source_frame = pd.read_pickle(source)

        with open(cluster_source, "rb") as cluster_file:
            cluster_model = pickle.load(cluster_file)

        print("Encoding all movies")

        all_encodings = []
        clustering_memo = {}
        for _, row in source_frame.iterrows():
            try:
                id = row['Id']
                tokenized_plot = row['TokenizedPlot']

                movie_encoding = MovieEncoding()

                for token, pos in tokenized_plot.Tokens:
                    # to speed up computation, memoize clustering results
                    if (token, pos) not in clustering_memo:
                        word_vector = tokenized_plot.Vectors[(token, pos)]
                        dim = cluster_model.predict(np.array([word_vector]))
                        clustering_memo[(token, pos)] = dim
                    else:
                        dim = clustering_memo[(token, pos)]
                    movie_encoding.PlotEncoding[dim] += 1
                movie_encoding.PlotEncoding.normalize()

                for entity, label in tokenized_plot.Entities:
                    ent_encoding = EntityEncoding(entity, label)
                    movie_encoding.add_entity(ent_encoding)

                print(f"Encoded id={id}")

                all_encodings.append((id, movie_encoding))
            except:
                continue
        
        sink_frame = pd.DataFrame(all_encodings, columns=['Id', 'MovieEncoding'])
        sink_frame.to_pickle(sink)

    def setup(self):
        import os

        data_folder = "data"
        movie_data_csv = os.path.join(data_folder, "wiki_movie_info.csv")
        movie_info_bin = os.path.join(data_folder, "movie_info.bin")
        tokenized_plots_bin = os.path.join(data_folder, "tokenized_plots.bin")
        word_vectors_bin = os.path.join(data_folder, "word_vectors.bin")
        cluster_model_bin = os.path.join(data_folder, "cluster_model.bin")
        cluster_scores_bin = os.path.join(data_folder, "cluster_scores.bin")
        movie_encodings_bin = os.path.join(data_folder, "movie_encodings.bin")

        self.load_all_movie_info(source=movie_data_csv, sink=movie_info_bin)
        
        tokenized_sinks = []
        vector_sinks = []
        rough_count = 34500
        step = 500
        for start, end in zip(range(0, rough_count+1, step), range(step, rough_count+step+1, step)):
            this_tokenized_sink = os.path.join(data_folder, f"tokenized_plots_{start}_{end-1}.bin")
            this_vector_sink = os.path.join(data_folder, f"word_vectors_{start}_{end-1}.bin")
            tokenized_sinks.append(this_tokenized_sink)
            vector_sinks.append(this_vector_sink)
            self.tokenize_all_plots_plus_vectors(source=movie_info_bin, sink=this_tokenized_sink, vector_sink=this_vector_sink, start_idx=start, end_idx=end)
        self.combine_tokenized_results(sources=tokenized_sinks, vector_sources=vector_sinks, sink=tokenized_plots_bin, vector_sink=word_vectors_bin)

        self.train_cluster_model_on_vectors(source=word_vectors_bin, sink=cluster_model_bin, score_sink=cluster_scores_bin, min_clusters=7000, max_clusters=15000, cluster_step=500)
        self.encode_all_movies(source=tokenized_plots_bin, vector_source=word_vectors_bin, cluster_source=cluster_model_bin, sink=movie_encodings_bin)

if __name__ == '__main__':
    setup = MovieServiceSetup()