import importlib

from colorama import Fore, Style
import matplotlib
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from prompt_toolkit import prompt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Chatbot:
    def __init__(self, local_vars, config_file = 'chatbot_config'):

        self.local_vars = local_vars

        self.conf = importlib.import_module(config_file)

        self.all_variables = self.conf.all_variables

        self.graph_data = self.process_graph_data(self.conf.graph_data_raw)
        self.graph_data_edges = [ member for member in self.graph_data if "start_states" in member]
        self.graph_data_nodes = [ member for member in self.graph_data if "intent" in member]

        # cosine tfidf model
        self.word_vectorizer = TfidfVectorizer()
        self.all_patterns = [pat for edge in self.graph_data_edges for pat in edge["patterns"]]
        self.word_vectorizer.fit(self.all_patterns)

        # add tfidf vectors to graph_data_edges
        for edge in self.graph_data_edges:
            patterns = edge["patterns"]
            pattern_vectors = self.word_vectorizer.transform(patterns)
            edge["pattern_vectors"] = pattern_vectors

        # open file for texts not understood
        self.file_not_understood = open("not_understood.txt", "a")

    def __del__(self):
        self.file_not_understood.close()

    def process_graph_data(self, graph_data):
        # replace ["*"] in start_states by actual list of all states
        all_intents = [member["intent"] for member in graph_data if "intent" in member]
        for member in graph_data:
            if "start_states" in member and member["start_states"] == ["*"]:
                member["start_states"] = all_intents
        return graph_data

    @staticmethod
    def print_subtle(*text, **kwargs):
        print(Fore.BLUE, *text , Style.RESET_ALL, **kwargs)

    def get_possible_next_pattern_vectors(self, curr_state, curr_contexts):
        # returns [(pat_vec, pat, end_state)]
        next_states = [ (edge["pattern_vectors"][i_vec],
                        edge["patterns"][i_vec],
                        edge["end_state"])
                        for edge in self.graph_data_edges
                        for i_vec in range(edge["pattern_vectors"].shape[0])
                        if curr_state in edge["start_states"]
                        and set(self.get_field_from_intent("context_require", edge["end_state"])).issubset(curr_contexts)]
        return next_states

    def get_possible_actions(self, curr_state, curr_contexts):
        "get only one pattern per edge to display to the user"
        next_actions = [ edge["patterns"][0]
                        for edge in self.graph_data_edges
                        if curr_state in edge["start_states"]
                        and set(self.get_field_from_intent("context_require", edge["end_state"])).issubset(curr_contexts)]
        return next_actions

    def get_closest_command(self, possible_next_pattern_vectors: list, inp:str):
        input_vector = self.word_vectorizer.transform([inp])
        all_distances = [(cosine_similarity(input_vector, pat_vec)[0][0], pat, end_state)
                            for pat_vec, pat, end_state in possible_next_pattern_vectors ]
        max_command = max(all_distances, key=lambda l: l[0])
        return max_command

    def get_field_from_intent(self, field_name, intent, default=[]):
        response = [node.get(field_name, default) for node in self.graph_data_nodes
                        if node['intent'] == intent]
        assert(len(response)==1)
        return response[0]

    def run(self):
        curr_state = "entry"
        curr_contexts = set()

        continue_flag = True

        while(continue_flag):
            self.print_subtle("-----------------------------------")
            self.print_subtle("current State", curr_state)
            self.print_subtle("current Contexts", curr_contexts)

            # possible_next_pattern_vectors = get_possible_next_pattern_vectors_old(curr_state)
            possible_next_pattern_vectors = self.get_possible_next_pattern_vectors(curr_state, curr_contexts)
            possible_next_states = list(set([ns for pat_vec, pat, ns in possible_next_pattern_vectors]))
            possible_things_to_do = self.get_possible_actions(curr_state, curr_contexts)
            self.print_subtle("Things to do: " + ', '.join(possible_things_to_do))

            inp = input('> ')
            if inp == "":
                # https://pythonspot.com/speech-recognition-using-google-speech-api/
                try:
                    import speech_recognition as sr

                    # Record Audio
                    r = sr.Recognizer()
                    with sr.Microphone() as source:
                        print("Say something!")
                        audio = r.listen(source)

                # Speech recognition using Google Speech Recognition
                    # for testing purposes, we're just using the default API key
                    # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
                    # instead of `r.recognize_google(audio)`
                    inp = r.recognize_google(audio)
                    print(inp)
                except OSError:
                    print("Most likely No Default Input Device Available")
                except sr.UnknownValueError:
                    print("Google Speech Recognition could not understand audio")
                except sr.RequestError as e:
                    print("Could not request results from Google Speech Recognition service; {0}".format(e))

            rating, pat, next_state = self.get_closest_command(possible_next_pattern_vectors, inp)
            required_contexts = self.get_field_from_intent("context_require", next_state)

            if inp == 'end' or inp == 'exit':
                continue_flag = False
                continue
            if rating < 0.6:
                print("Sorry, didn't understand you!")
                self.file_not_understood.write(inp + "\n")
                continue
            if not set(required_contexts).issubset(curr_contexts):
                lacking_context = set(required_contexts)-curr_contexts
                print("Sorry, you lack context", lacking_context, "to do this")
                continue

            parser = self.get_field_from_intent("code_command",
                                            next_state,
                                            default=lambda all_variables, inp, local_vars: all_variables)
            self.all_variables = parser(self.all_variables, inp, self.local_vars)

            curr_state = next_state
            curr_contexts |= set(self.get_field_from_intent("context_set", next_state))
            print(self.get_field_from_intent("response", curr_state, ""))
        print("bye")


#######################################################################################################
# Graveyard

def get_possible_next_states(curr_state):
    edges = [ member for member in graph_data if "start_states" in member]
    next_states = [ member["end_state"] for member in edges
                    if curr_state in member["start_states"]]
    return next_states


def get_possible_next_patterns(curr_state):
    edges = [ member for member in graph_data if "start_states" in member]
    next_states = [ (patt, member["end_state"]) for member in edges for patt in member["patterns"]
                    if curr_state in member["start_states"]]
    return next_states


def get_possible_next_pattern_vectors_old(curr_state):
    # returns [(pat_vec, pat, end_state)]
    next_states = [ (member["pattern_vectors"][i_vec],
                    member["patterns"][i_vec],
                    member["end_state"])
                    for member in graph_data_edges
                    for i_vec in range(member["pattern_vectors"].shape[0])
                    if curr_state in member["start_states"]]
    return next_states
