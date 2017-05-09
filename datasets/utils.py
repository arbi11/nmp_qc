#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
    utils.py: Functions to process dataset graphs.

    Usage:

"""

from __future__ import print_function

import rdkit
import torch
from joblib import Parallel, delayed
import multiprocessing
import networkx as nx

import numpy as np


__author__ = "Pau Riba, Anjan Dutta"
__email__ = "priba@cvc.uab.cat, adutta@cvc.uab.cat"


def qm9_nodes(g, hydrogen=False):
    h = []
    for n, d in g.nodes_iter(data=True):
        h_t = []
        # Atom type (One-hot H, C, N, O F)
        h_t += [int(d['a_type'] == x) for x in ['H', 'C', 'N', 'O', 'F']]
        # Atomic number
        h_t.append(d['a_num'])
        # Partial Charge
        h_t.append(d['pc'])
        # Acceptor
        h_t.append(d['acceptor'])
        # Donor
        h_t.append(d['donor'])
        # Aromatic
        h_t.append(int(d['aromatic']))
        # Hybradization
        h_t += [int(d['hybridization'] == x) for x in [rdkit.Chem.rdchem.HybridizationType.SP, rdkit.Chem.rdchem.HybridizationType.SP2, rdkit.Chem.rdchem.HybridizationType.SP3]]
        # If number hydrogen is used as a
        if hydrogen:
            h_t.append(d['num_h'])
        h.append(h_t)
    return h


def qm9_edges(g, e_representation='chem_graph'):
    remove_edges = []
    e={}    
    for n1, n2, d in g.edges_iter(data=True):
        e_t = []
        # Raw distance function
        if e_representation == 'chem_graph':
            if d['b_type'] is None:
                remove_edges += [(n1, n2)]
            else:
                e_t += [i+1 for i, x in enumerate([rdkit.Chem.rdchem.BondType.SINGLE, rdkit.Chem.rdchem.BondType.DOUBLE,
                                                rdkit.Chem.rdchem.BondType.TRIPLE, rdkit.Chem.rdchem.BondType.AROMATIC])
                        if x == d['b_type']]
        elif e_representation == 'distance_bin':
            if d['b_type'] is None:
                step = (6-2)/8.0
                start = 2
                b = 9
                for i in range(0, 9):
                    if d['distance'] < (start+i*step):
                        b = i
                        break
                e_t.append(b+5)
            else:
                e_t += [i+1 for i, x in enumerate([rdkit.Chem.rdchem.BondType.SINGLE, rdkit.Chem.rdchem.BondType.DOUBLE,
                                                   rdkit.Chem.rdchem.BondType.TRIPLE, rdkit.Chem.rdchem.BondType.AROMATIC])
                        if x == d['b_type']]
        elif e_representation == 'raw_distance':
            if d['b_type'] is None:
                remove_edges += [(n1, n2)]
            else:
                e_t.append(d['distance'])
                e_t += [int(d['b_type'] == x) for x in [rdkit.Chem.rdchem.BondType.SINGLE, rdkit.Chem.rdchem.BondType.DOUBLE,
                                                        rdkit.Chem.rdchem.BondType.TRIPLE, rdkit.Chem.rdchem.BondType.AROMATIC]]
        else:
            print('Incorrect Edge representation transform')
            quit()
        if e_t:
            e[(n1, n2)] = e_t
    for edg in remove_edges:
        g.remove_edge(*edg)
    return nx.to_numpy_matrix(g), e
    
    
def mutag_nodes(g):
    h = []
    for n, d in g.nodes_iter(data=True):
        h_t = []
        h_t.append(d['label'])
        h.append(h_t)
        
    return torch.FloatTensor(h)
    
    
def mutag_edges(g):
    e = {}
    for n1, n2, d in g.edges_iter(data=True):
        e_t = []
        e_t.append(d['label'])
        e[(n1,n2)] = torch.FloatTensor(e_t)
        
    return g, e
    
    
def gwhist_nodes(g):
    h = []
    for n, d in g.nodes_iter(data=True):
        h_t = []
        h_t += [float(x) for x in d['labels']]
        h.append(h_t)
        
    return torch.FloatTensor(h)
    

def gwhist_edges(g):
    e = {}
    for n1, n2, d in g.edges_iter(data=True):
        e_t = []
        e_t += [10]
        e[(n1,n2)] = torch.FloatTensor(e_t)
        
    return g, e
    

def normalize_data(data, mean, std):
    data_norm = (data-mean)/std
    return data_norm


def get_values(obj, start, end, prop):
    vals = []
    for i in range(start, end):
        v = {}
        if 'degrees' in prop:
            v['degrees'] = set(map(len, obj[i][0][0]))
        if 'target_mean' in prop or 'target_std' in prop:
            v['params'] = obj[i][1]
        vals.append(v)
    return vals


def get_graph_stats(graph_obj_handle, prop='degrees'):
    # if prop == 'degrees':
    num_cores = multiprocessing.cpu_count()
    inputs = [int(i*len(graph_obj_handle)/num_cores) for i in range(num_cores) ] +[ len(graph_obj_handle)]
    res = Parallel(n_jobs = num_cores)(delayed(get_values)(graph_obj_handle, inputs[i], inputs[i+1], prop) for i in range(num_cores))

    stat_dict = {}

    if 'degrees' in prop:
        stat_dict['degrees'] = list(set([d for core_res in res for file_res in core_res for d in file_res['degrees']]))

    if 'target_mean' in prop or 'target_std' in prop:
        param = np.array([file_res['params'] for core_res in res for file_res in core_res])
    if 'target_mean' in prop:
        stat_dict['target_mean'] = np.mean(param, axis=0)
    if 'target_std' in prop:
        stat_dict['target_std'] = np.std(param, axis=0)

    return stat_dict


def collate_g(batch):

    batch_sizes = np.max(np.array([[len(input_b[1]), len(input_b[1][0]), len(input_b[2]),
                                len(list(input_b[2].values())[0])]  for (input_b, target_b) in batch]), axis=0)

    g = np.zeros((len(batch), batch_sizes[0], batch_sizes[0]))
    h = np.zeros((len(batch), batch_sizes[0], batch_sizes[1]))
    e = np.zeros((len(batch), batch_sizes[0], batch_sizes[0], batch_sizes[3]))
    target = np.zeros((len(batch), len(batch[0][1])))

    for i in range(len(batch)):

        num_nodes = len(batch[i][0][1])

        # Adjacency list
        g[i, 0:num_nodes, 0:num_nodes] = batch[i][0][0]

        # Node features
        h[i, 0:num_nodes, :] = batch[i][0][1]

        # Edges
        for edge in batch[i][0][2].keys():
            e[i, edge[0], edge[1], :] = batch[i][0][2][edge]
            e[i, edge[1], edge[0], :] = batch[i][0][2][edge]

        # Target
        target[i, :] = batch[i][1]

    g = torch.FloatTensor(g)
    h = torch.FloatTensor(h)
    e = torch.FloatTensor(e)
    target = torch.FloatTensor(target)

    return g, h, e, target


