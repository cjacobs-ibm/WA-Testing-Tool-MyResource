#! /usr/bin/python
# coding: utf-8

# Copyright 2019 IBM All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Generate confusion matrix from intent training/testing results
"""
import csv
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import json
from argparse import ArgumentParser
from sklearn.metrics import confusion_matrix
from __init__ import UTF_8

def cell_to_str(x):
    # Removes 0 from confusion matrix
    if x == 0:
        return ""
    return str(x)

def func(args):
    # Load the mapping JSON
    with open('./actions.json', 'r') as json_file:
        intent_mapping = json.load(json_file)
    
    in_df = pd.read_csv(args.in_file, quoting=csv.QUOTE_ALL,
                        encoding=UTF_8, keep_default_na=False)
    # Look for target columns
    if args.test_column not in in_df or args.golden_column not in in_df:
        raise ValueError('Missing required columns')
    
     # Replace `golden intent` with `action title`
    in_df[args.golden_column] = in_df[args.golden_column].map(intent_mapping).fillna(in_df[args.golden_column])  # Default to original value if no mapping
    in_df[args.test_column] = in_df[args.test_column].map(intent_mapping).fillna(in_df[args.test_column])

    labels = in_df[args.golden_column].drop_duplicates().sort_values()

    cm_args = {}
    cm_args['y_true'] = in_df[args.golden_column]
    cm_args['y_pred'] = in_df[args.test_column]
    cm_args['labels'] = labels

    # Use a column called 'weight' to scale the per-intent metrics
    if 'weight' in in_df:
        cm_args['sample_weight'] = in_df['weight']

    output_matrix = confusion_matrix(**cm_args)

    #Thanks to https://stackoverflow.com/questions/50325786/sci-kit-learn-how-to-print-labels-for-confusion-matrix for this clever line of python
    index_labels  = ['golden:{:}'.format(x) for x in labels]
    column_labels = [  'test:{:}'.format(x) for x in labels] 

    out_df = pd.DataFrame(output_matrix, 
                           index=index_labels,
                           columns=column_labels)

    out_df.to_csv(args.out_file, encoding='utf-8', quoting=csv.QUOTE_ALL, index=index_labels, columns=column_labels)
    print ("Wrote confusion matrix output to {}.".format(args.out_file))

    #Plot a normalized confusion matrix as a heatmap
    plt.figure(figsize = (10,10))

    # Create multiple normalizations
    orig_cm = pd.DataFrame(output_matrix, index=index_labels, columns=column_labels)
    df_cm = orig_cm.copy(deep=True).to_numpy()
    global_scaled_cm = df_cm/np.sum(df_cm) # Normalize on total number of samples.  Makes the higher-volume parts stand out.
    intent_scaled_cm = df_cm.astype('float') / df_cm.sum(axis=1)[:, np.newaxis] # Makes single-intent accuracy of 100% full black
    sns.set(font_scale=1)

    hm_args = {}
    hm_args['cmap'] = "Greys"      # Grayscale prints best
    hm_args['cbar'] = False        # Does not append legend
    hm_args['linewidths'] = 0.1    # Border on each cell
    hm_args['linecolor'] = 'black' # Black lines
    hm_args['xticklabels'] = column_labels # Test/Predicted intent
    hm_args['yticklabels'] = index_labels  # Golden/Expected intent

    # Add labels if it does not clutter the graph too much.  After 10-15 classes the labels get hard to read.
    if(len(index_labels) < 12): 
        labels_cm = orig_cm.copy(deep=True).applymap(cell_to_str) # Replace 0 with blank to declutter the visualization
        hm_args['annot'] = labels_cm   # Label each cell
        hm_args['fmt'] = ''            # Pass only the label string to the cell

    # First create the original "intent scaled" version (100% on intent = black)
    hm = sns.heatmap(intent_scaled_cm, **hm_args)
    hm.set_yticklabels(hm.get_yticklabels(), rotation=0)
    hm.set_xticklabels(hm.get_xticklabels(), rotation=90) #Rotation 90 degrees to vertical, easier to read

    plt.title("Normalized Confusion Matrix")
    plt.tight_layout()
    plt.autoscale()
    out_image_file = args.out_file[:-4] + ".png"
    plt.savefig(out_image_file,bbox_inches='tight',dpi=400)
   
    print ("Wrote confusion matrix diagram to {}.".format(out_image_file))

    # Then create the new "global scaled" version (highest volume == darkest)
    hm = sns.heatmap(global_scaled_cm, **hm_args)
    hm.set_yticklabels(hm.get_yticklabels(), rotation=0)
    hm.set_xticklabels(hm.get_xticklabels(), rotation=90) #Rotation 90 degrees to vertical, easier to read

    plt.title("Normalized Scaled Confusion Matrix")
    plt.tight_layout()
    plt.autoscale()
    out_image_file = args.out_file[:-4] + "_scaled.png"
    plt.savefig(out_image_file,bbox_inches='tight',dpi=400)
   
    print ("Wrote global-scaled confusion matrix diagram to {}.".format(out_image_file))

def create_parser():
    parser = ArgumentParser(
        description='Generate confusion matrix')
    parser.add_argument('-i', '--in_file', type=str, required=True,
                        help='File that contains intent test and golden data')
    parser.add_argument('-o', '--out_file', type=str,
                        help='Output file path',
                        default='confusion-matrix.csv')
    parser.add_argument('-t', '--test_column', type=str,
                        default='predicted intent',
                        help='Test column name')
    parser.add_argument('-g', '--golden_column', type=str,
                        default='golden intent',
                        help='Golden column name')
    #parser.add_argument('-p', '--partial_credit_on', type=str,
    #                    help='Use only if partial credit scoring ')
    return parser


if __name__ == '__main__':
    ARGS = create_parser().parse_args()
    func(ARGS)
