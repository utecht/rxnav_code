import pickle

def save(drugs):
	with open('rxnorm_cache.pickle', 'wb') as outf:
		pickle.dump(drugs, outf)


drugs = {}
#with open('rxnorm_cache.pickle', 'rb') as inf:
#	drugs = pickle.load(inf)

save(drugs)

