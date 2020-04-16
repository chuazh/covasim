'''
Base classes for Covasim.
'''

import datetime as dt
import numpy as np # Needed for a few things not provided by pl
import sciris as sc
import pandas as pd
from . import utils as cvu
from . import defaults as cvd

# Specify all externally visible classes this file defines
__all__ = ['ParsObj', 'Result', 'BaseSim', 'BasePeople', 'Person', 'TransTree']


#%% Define simulation classes

class ParsObj(sc.prettyobj):
    '''
    A class based around performing operations on a self.pars dict.
    '''

    def __init__(self, pars):
        self.update_pars(pars, create=True)
        return

    def __getitem__(self, key):
        ''' Allow sim['par_name'] instead of sim.pars['par_name'] '''
        return self.pars[key]

    def __setitem__(self, key, value):
        ''' Ditto '''
        if key in self.pars:
            self.pars[key] = value
        else:
            suggestion = sc.suggest(key, self.pars.keys())
            if suggestion:
                errormsg = f'Key "{key}" not found; did you mean "{suggestion}"?'
            else:
                all_keys = '\n'.join(list(self.pars.keys()))
                errormsg = f'Key "{key}" not found; available keys:\n{all_keys}'
            raise KeyError(errormsg)
        return

    def update_pars(self, pars=None, create=False):
        '''
        Update internal dict with new pars.

        Args:
            pars (dict): the parameters to update (if None, do nothing)
            create (bool): if create is False, then raise a KeyError if the key does not already exist
        '''
        if pars is not None:
            if not isinstance(pars, dict):
                raise TypeError(f'The pars object must be a dict; you supplied a {type(pars)}')
            if not hasattr(self, 'pars'):
                self.pars = pars
            if not create:
                available_keys = list(self.pars.keys())
                mismatches = [key for key in pars.keys() if key not in available_keys]
                if len(mismatches):
                    errormsg = f'Key(s) {mismatches} not found; available keys are {available_keys}'
                    raise KeyError(errormsg)
            self.pars.update(pars)
        return


class Result(object):
    '''
    Stores a single result -- by default, acts like an array.

    Args:
        name (str): name of this result, e.g. new_infections
        values (array): array of values corresponding to this result
        npts (int): if values is None, precreate it to be of this length
        scale (str): whether or not the value scales by population size; options are "dynamic", "static", or False
        color (str or array): default color for plotting (hex or RGB notation)

    Example:
        import covasim as cv
        r1 = cv.Result(name='test1', npts=10)
        r1[:5] = 20
        print(r2.values)
        r2 = cv.Result(name='test2', values=range(10))
        print(r2)
    '''

    def __init__(self, name=None, values=None, npts=None, scale='dynamic', color=None):
        self.name =  name  # Name of this result
        self.scale = scale # Whether or not to scale the result by the scale factor
        if color is None:
            color = '#000000'
        self.color = color # Default color
        if values is None:
            if npts is not None:
                values = np.zeros(int(npts)) # If length is known, use zeros
            else:
                values = [] # Otherwise, empty
        self.values = np.array(values, dtype=float) # Ensure it's an array
        return

    def __repr__(self, *args, **kwargs):
        ''' Use pretty repr, like sc.prettyobj, but displaying full values '''
        output  = sc.prepr(self, skip='values')
        output += 'values:\n' + repr(self.values)
        return output

    def __getitem__(self, *args, **kwargs):
        return self.values.__getitem__(*args, **kwargs)

    def __setitem__(self, *args, **kwargs):
        return self.values.__setitem__(*args, **kwargs)

    @property
    def npts(self):
        return len(self.values)


class BaseSim(ParsObj):
    '''
    The BaseSim class handles the running of the simulation: the number of people,
    number of time points, and the parameters of the simulation.
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs) # Initialize and set the parameters as attributes
        return

    def set_seed(self, seed=-1):
        '''
        Set the seed for the random number stream from the stored or supplied value

        Args:
            seed (None or int): if no argument, use current seed; if None, randomize; otherwise, use and store supplied seed

        Returns:
            None
        '''
        # Unless no seed is supplied, reset it
        if seed != -1:
            self['rand_seed'] = seed
        cvu.set_seed(self['rand_seed'])
        return

    @property
    def n(self):
        ''' Count the number of people -- if it fails, assume none '''
        try: # By default, the length of the people dict
            return len(self.people)
        except: # If it's None or missing
            return 0

    @property
    def npts(self):
        ''' Count the number of time points '''
        try:
            return int(self['n_days'] + 1)
        except:
            return 0

    @property
    def tvec(self):
        ''' Create a time vector '''
        try:
            return np.arange(self.npts)
        except:
            return np.arange([])

    @property
    def datevec(self):
        '''
        Create a vector of dates

        Returns:
            Array of `datetime` instances containing the date associated with each
            simulation time step

        '''
        try:
            return self['start_day'] + self.tvec * dt.timedelta(days=1)
        except:
            return []


    def inds2dates(self, inds, dateformat=None):
        ''' Convert a set of indices to a set of dates '''

        if sc.isnumber(inds): # If it's a number, convert it to a list
            inds = sc.promotetolist(inds)

        if dateformat is None:
            dateformat = '%b-%d'

        dates = []
        for ind in inds:
            tmp = self['start_day'] + dt.timedelta(days=int(ind))
            dates.append(tmp.strftime(dateformat))
        return dates


    def result_keys(self):
        ''' Get the actual results objects, not other things stored in sim.results '''
        keys = [key for key in self.results.keys() if isinstance(self.results[key], Result)]
        return keys


    def contact_keys(self):
        ''' Get the available contact keys -- set by beta_layer rather than contacts since only the former is required '''
        keys = list(self['beta_layer'].keys())
        return keys


    def _make_resdict(self, for_json=True):
        '''
        Convert results to dict

        The results written to Excel must have a regular table shape, whereas
        for the JSON output, arbitrary data shapes are supported.

        Args:
            for_json: If False, only data associated with Result objects will be included in the converted output

        Returns:
            resdict (dict): Dictionary representation of the results

        '''
        resdict = {}
        resdict['t'] = self.results['t'] # Assume that there is a key for time

        if for_json:
            resdict['timeseries_keys'] = self.result_keys()
        for key,res in self.results.items():
            if isinstance(res, Result):
                resdict[key] = res.values
            elif for_json:
                if key == 'date':
                    resdict[key] = [str(d) for d in res] # Convert dates to strings
                else:
                    resdict[key] = res
        return resdict


    def _make_pardict(self):
        '''
        Return parameters for JSON export

        This method is required so that interventions can specify
        their JSON-friendly representation

        Returns:

        '''
        pardict = {}
        for key in self.pars.keys():
            if key == 'interventions':
                pardict[key] = [intervention.to_json() for intervention in self.pars[key]]
            elif key == 'start_day':
                pardict[key] = str(self.pars[key])
            else:
                pardict[key] = self.pars[key]
        return pardict


    def to_json(self, filename=None, keys=None, tostring=True, indent=2, verbose=False, *args, **kwargs):
        '''
        Export results as JSON.

        Args:
            filename (str): if None, return string; else, write to file
            keys (str or list): attributes to write to json (default: results, parameters, and summary)
            tostring (bool): if not writing to file, whether to write to string (alternative is sanitized dictionary)
            indent (int): if writing to file, how many indents to use per nested level
            verbose (bool): detail to print
            args (list): passed to savejson()
            kwargs (dict): passed to savejson()

        Returns:
            A unicode string containing a JSON representation of the results,
            or writes the JSON file to disk

        Examples:
            string = sim.to_json()
            sim.to_json('results.json')
            sim.to_json('summary.json', keys='summary')
        '''

        # Handle keys
        if keys is None:
            keys = ['results', 'pars', 'summary']
        keys = sc.promotetolist(keys)

        # Convert to JSON-compatibleformat
        d = {}
        for key in keys:
            if key == 'results':
                resdict = self._make_resdict()
                d['results'] = resdict
            elif key in ['pars', 'parameters']:
                pardict = self._make_pardict()
                d['parameters'] = pardict
            elif key == 'summary':
                d['summary'] = dict(sc.dcp(self.summary))
            else:
                try:
                    d[key] = sc.sanitizejson(getattr(self, key))
                except Exception as E:
                    errormsg = f'Could not convert "{key}" to JSON: {str(E)}; continuing...'
                    print(errormsg)

        if filename is None:
            output = sc.jsonify(d, tostring=tostring, indent=indent, verbose=verbose, *args, **kwargs)
        else:
            output = sc.savejson(filename=filename, obj=d, indent=indent, *args, **kwargs)

        return output


    def to_excel(self, filename=None):
        '''
        Export results as XLSX

        Args:
            filename (str): if None, return string; else, write to file

        Returns:
            An sc.Spreadsheet with an Excel file, or writes the file to disk

        '''
        resdict = self._make_resdict(for_json=False)
        result_df = pd.DataFrame.from_dict(resdict)
        result_df.index = self.tvec
        result_df.index.name = 'Day'

        par_df = pd.DataFrame.from_dict(sc.flattendict(self.pars, sep='_'), orient='index', columns=['Value'])
        par_df.index.name = 'Parameter'

        spreadsheet = sc.Spreadsheet()
        spreadsheet.freshbytes()
        with pd.ExcelWriter(spreadsheet.bytes, engine='xlsxwriter') as writer:
            result_df.to_excel(writer, sheet_name='Results')
            par_df.to_excel(writer, sheet_name='Parameters')
        spreadsheet.load()

        if filename is None:
            output = spreadsheet
        else:
            output = spreadsheet.save(filename)

        return output


    def shrink(self, skip_attrs=None, in_place=True):
        '''
        "Shrinks" the simulation by removing the people, and returns
        a copy of the "shrunken" simulation. Used to reduce the memory required
        for saved files.

        Args:
            skip_attrs (list): a list of attributes to skip in order to perform the shrinking; default "people"

        Returns:
            shrunken_sim (Sim): a Sim object with the listed attributes removed
        '''

        # By default, skip people (~90%) and uids (~9%)
        if skip_attrs is None:
            skip_attrs = ['popdict', 'people']

        # Create the new object, and copy original dict, skipping the skipped attributes
        if in_place:
            for attr in skip_attrs:
                setattr(self, attr, None)
            return
        else:
            shrunken_sim = object.__new__(self.__class__)
            shrunken_sim.__dict__ = {k:(v if k not in skip_attrs else None) for k,v in self.__dict__.items()}
            return shrunken_sim


    def save(self, filename=None, keep_population=False, skip_attrs=None, **kwargs):
        '''
        Save to disk as a gzipped pickle.

        Args:
            filename (str or None): the name or path of the file to save to; if None, uses stored
            kwargs: passed to makefilepath()

        Returns:
            filename (str): the validated absolute path to the saved file

        Example:
            sim.save() # Saves to a .sim file with the date and time of creation by default
        '''
        if filename is None:
            filename = self.filename
        filename = sc.makefilepath(filename=filename, **kwargs)
        self.filename = filename # Store the actual saved filename
        if skip_attrs or not keep_population:
            obj = self.shrink(skip_attrs=skip_attrs, in_place=False)
        else:
            obj = self
        sc.saveobj(filename=filename, obj=obj)
        return filename


    @staticmethod
    def load(filename, **kwargs):
        '''
        Load from disk from a gzipped pickle.

        Args:
            filename (str): the name or path of the file to save to
            keywords: passed to makefilepath()

        Returns:
            sim (Sim): the loaded simulation object

        Example:
            sim = cv.Sim.load('my-simulation.sim')
        '''
        filename = sc.makefilepath(filename=filename, **kwargs)
        sim = sc.loadobj(filename=filename)
        return sim


#%% Define people classes

class BasePeople(sc.prettyobj):
    '''
    A class to handle all the boilerplate for people -- note that everything
    interesting happens in the People class.
    '''

    def __init__(self, pars=None, pop_size=None, *args, **kwargs):

        # Handle pars and population size
        self.pars = pars
        if pop_size is None:
            if pars is not None:
                pop_size = pars['pop_size']
            else:
                pop_size = 0
        pop_size = int(pop_size)
        self.pop_size = pop_size

        # Other initialization
        self.t = 0 # Keep current simulation time
        self._lock = False # Prevent further modification of keys
        self._default_dtype = np.float32 # For performance -- 2x faster than float32, the default
        self.keylist = cvd.PeopleKeys() # Store list of keys and dtypes
        self.layer_info = self.keylist.contacts
        self.contacts = None
        self.init_contacts() # Initialize the contacts
        self.transtree = TransTree(pop_size=pop_size) # Initialize the transmission tree

        return


    def __getitem__(self, key):
        ''' Allow people['attr'] instead of getattr(people, 'attr') '''
        try:
            return self.__dict__[key]
        except:
            errormsg = f'Key "{key}" is not a valid attribute of people'
            raise AttributeError(errormsg)


    def __setitem__(self, key, value):
        ''' Ditto '''
        if self._lock and key not in self.__dict__:
            errormsg = f'Key "{key}" is not a valid attribute of people'
            raise AttributeError(errormsg)
        self.__dict__[key] = value
        return


    def __len__(self):
        ''' This is just a scalar, but validate() and resize() make sure it's right '''
        return self.pop_size


    def __iter__(self):
        ''' Define the iterator to just be the indices of the array '''
        return iter(range(len(self)))


    def __add__(self, people2):
        ''' Combine two people arrays '''
        newpeople = sc.dcp(self)
        for key in self.keys():
            newpeople.set(key, np.concatenate([newpeople[key], people2[key]]), die=False) # Allow size mismatch

        # Validate
        newpeople.pop_size += people2.pop_size
        newpeople.validate()

        # Reassign UIDs so they're unique
        newpeople.set('uid', np.arange(len(newpeople)))

        return newpeople


    def set(self, key, value, die=True):
        ''' Ensure sizes and dtypes match '''
        current = self[key]
        value = np.array(value, dtype=self._dtypes[key]) # Ensure it's the right type
        if die and len(value) != len(current):
            errormsg = f'Length of new array does not match current ({len(value)} vs. {len(current)})'
            raise IndexError(errormsg)
        self[key] = value
        return


    def get(self, key):
        ''' Convenience method '''
        return self[key]


    def true(self, key):
        ''' Return indices matching the condition '''
        return self[key].nonzero()[0]


    def false(self, key):
        ''' Return indices not matching the condition '''
        return ~self[key].nonzero()[0]


    def count(self,key):
        ''' Count the number of people for a given key '''
        return (self[key]>0).sum()


    def keys(self, which=None):
        ''' Returns the name of the states '''
        if which is None:
            return self.keylist.all_states[:]
        else:
            return getattr(self.keylist, which)[:]


    def contact_keys(self):
        ''' Get the available contact keys -- set by beta_layer rather than contacts since only the former is required '''
        try:
            keys = list(self.pars['beta_layer'].keys())
        except: # If not initialized
            keys = []
        return keys


    def index(self):
        ''' The indices of the array '''
        return np.arange(len(self))


    def validate(self, die=True, verbose=False):
        expected_len = len(self)
        for key in self.keys():
            actual_len = len(self[key])
            if actual_len != expected_len:
                if die:
                    errormsg = f'Length of key "{key}" did not match population size ({actual_len} vs. {expected_len})'
                    raise IndexError(errormsg)
                else:
                    if verbose:
                        print(f'Resizing "{key}" from {actual_len} to {expected_len}')
                    self.resize(keys=key)
        return


    def resize(self, pop_size=None, keys=None):
        ''' Resize arrays if any mismatches are found '''
        if pop_size is None:
            pop_size = len(self)
        self.pop_size = pop_size
        if keys is None:
            keys = self.keys()
        keys = sc.promotetolist(keys)
        for key in keys:
            self[key].resize(pop_size, refcheck=False)
        return


    def to_df(self):
        ''' Convert to a Pandas dataframe '''
        df = pd.DataFrame.from_dict({key:self[key] for key in self.keys()})
        return df


    def to_arr(self):
        ''' Return as numpy array '''
        arr = np.empty((len(self), len(self.keys())), dtype=np.float32)
        for k,key in enumerate(self.keys()):
            if key == 'uid':
                arr[:,k] = np.arange(len(self))
            else:
                arr[:,k] = self[key]
        return arr


    def person(self, ind):
        ''' Method to create person from the people '''
        p = Person()
        for key in self.keylist.all_states:
            setattr(p, key, self[key][ind])
        return p


    def to_people(self):
        ''' Return all people as a list '''
        people = []
        for p in self:
            person = self.person(p)
            people.append(person)
        return people


    def from_people(self, people, resize=True):
        ''' Convert a list of people back into a People object '''

        # Handle population size
        pop_size = len(people)
        if resize:
            self.resize(pop_size=pop_size)

        # Iterate over people -- slow!
        for p,person in enumerate(people):
            for key in self.keys():
                self[key][p] = getattr(person, key)

        return


    def init_contacts(self, output=False, keys=None):
        ''' Initialize the contacts dataframe with the correct columns and data types '''

        # Handle keys -- by default, all
        if keys is None:
            keys = self.contact_keys()
        keys = sc.promotetolist(keys)

        # Create the contacts dictionary
        contacts = Contacts()
        for key in keys:
            contacts[key] = Layer(layer_info=self.layer_info)

        # Handle output
        if output:
            return contacts
        else:
            if self.contacts is None: # Reset all
                self.contacts = contacts
            else: # Only replace specified keys
                for key,layer in contacts.items():
                    self.contacts[key] = layer
        return


    def add_contacts(self, contacts, key=None, beta=None):
        ''' Add new contacts to the array '''

        if key is None:
            key = self.contact_keys()[0]
        if key not in self.contacts:
            self.contacts[key] = Layer(layer_info=self.layer_info)

        # Validate the supplied contacts
        if isinstance(contacts, Contacts):
            new_contacts = contacts
        if isinstance(contacts, Layer):
            new_contacts = {}
            new_contacts[key] = contacts
        elif sc.checktype(contacts, 'array'):
            new_contacts = {}
            new_contacts[key] = pd.DataFrame(data=contacts)
        elif isinstance(contacts, dict):
            new_contacts = {}
            new_contacts[key] = pd.DataFrame.from_dict(contacts)
        elif isinstance(contacts, list): # Assume it's a list of contacts by person, not an edgelist
            new_contacts = self.make_edgelist(contacts) # Assume contains key info
        else:
            errormsg = f'Cannot understand contacts of type {type(contacts)}; expecting dataframe, array, or dict'
            raise TypeError(errormsg)

        # Ensure the columns are right and add values if supplied
        for lkey, new_layer in new_contacts.items():
            n = len(new_layer['p1'])
            if 'layer' not in new_layer:
                new_layer['layer'] = np.array([key]*n)
            if 'beta' not in new_layer or len(new_layer['beta']) != n:
                if beta is None:
                    beta = self.pars['beta_layer'][key]
                beta = np.float32(beta)
                new_layer['beta'] = np.ones(n, dtype=np.float32)*beta

            # Actually include them, and update properties if supplied
            for col in self.layer_info.keys():
                self.contacts[lkey][col] = np.concatenate([self.contacts[lkey][col], new_layer[col]])
            self.contacts[lkey].validate()

        return


    def make_edgelist(self, contacts):
        '''
        Parse a list of people with a list of contacts per person and turn it
        into an edge list.
        '''

        # Parse the list
        new_contacts = Contacts()
        lkeys = list(contacts[0].keys()) # Get the key list from the first contact
        for lkey in lkeys:
            new_contacts[lkey]['p1']    = [] # Person 1 of the contact pair
            new_contacts[lkey]['p2']    = [] # Person 2 of the contact pair
            new_contacts[lkey]['layer'] = [] # Layers

        for p,cdict in enumerate(contacts):
            for key,p_contacts in cdict.items():
                n = len(p_contacts) # Number of contacts
                new_contacts[lkey]['p1'].extend([p]*n) # e.g. [4, 4, 4, 4]
                new_contacts[lkey]['p2'].extend(p_contacts) # e.g. [243, 4538, 7,19]
                new_contacts[lkey]['layer'].extend([key]*n) # e.g. ['h', 'h', 'h', 'h']

        # Turn into a dataframe
        for lkey in lkeys:
            new_layer = Layer(layer_info=self.layer_info)
            for key,value in new_contacts[lkey].items():
                new_layer[key] = np.array(value, dtype=self.keylist.contacts[key])
            new_contacts[lkey] = new_layer

        return new_contacts


    @staticmethod
    def remove_duplicates(df):
        ''' Sort the dataframe and remove duplicates '''
        p1 = df[['p1', 'p2']].values.min(1) # Reassign p1 to be the lower-valued of the two contacts
        p2 = df[['p1', 'p2']].values.max(1) # Reassign p2 to be the higher-valued of the two contacts
        df['p1'] = p1
        df['p2'] = p2
        df.sort_values(['p1', 'p2'], inplace=True) # Sort by p1, then by p2
        df.drop_duplicates(['p1', 'p2'], inplace=True) # Remove duplicates
        df = df[df['p1'] != df['p2']] # Remove self connections
        df.reset_index(inplace=True, drop=True)
        return df


    def remove_dynamic_contacts(self, dynamic_keys='c'):
        ''' Remove all contacts labeled as dynamic '''
        dynamic_keys = sc.promotetolist(dynamic_keys)
        for key in dynamic_keys:
         if key in self.pars['contacts']:
            self.contacts.pop(key)
        return



class Person(sc.prettyobj):
    '''
    Class for a single person. Note: this is largely deprecated since sim.people
    is now based on arrays rather than being a list of people.
    '''
    def __init__(self, pars=None, uid=None, age=-1, sex=-1, contacts=None):
        self.uid         = uid # This person's unique identifier
        self.age         = float(age) # Age of the person (in years)
        self.sex         = int(sex) # Female (0) or male (1)
        self.contacts    = contacts # Contacts
        self.dyn_cont_ppl = {} # People who are contactable within the community.  Changes every step so has to be here.

        # Set states
        self.infected = [] #: Record the UIDs of all people this person infected
        self.infected_by = None #: Store the UID of the person who caused the infection. If None but person is infected, then it was an externally seeded infection

        return


class Contacts(dict):
    '''
    A simple (for now) class for storing different contact layers.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        return

    def __repr__(self):
        ''' Use odict repr'''
        return sc.odict.__repr__(self)

    def __getitem__(self, key):
        ''' Lightweight odict -- allow indexing by number '''
        try:
            return super().__getitem__(key)
        except KeyError as KE:
            try: # Assume it's an integer
                dictkey = list(self.keys())[key]
                return self[dictkey]
            except:
                raise KE # This is the original error


class Layer(dict):
    ''' A tiny class holding a single layer of contacts '''

    def __init__(self, layer_info, **kwargs):
        self.basekey = 'p1' # Assign a base key for calculating lengths and performing other operations
        self.layer_info = layer_info
        for key,dtype in self.layer_info.items():
            self[key] = np.empty((0,), dtype=dtype)

        for key,value in kwargs.items():
            self[key] = value

        return


    def __len__(self):
        try:
            return len(self[self.basekey])
        except:
            return 0


    def validate(self):
        ''' Check the integrity of the layer: right types, right lengths '''
        n = len(self[self.basekey])
        for key,dtype in self.layer_info.items():
            if dtype:
                assert self[key].dtype == dtype
            assert n == len(self[key])
        return


    def to_df(self):
        ''' Convert to dataframe '''
        df = pd.DataFrame.from_dict(self)
        return df


    def from_df(self, df):
        ''' Convert from dataframe '''
        for key in self.layer_info.keys():
            self[key] = df[key]
        return



class TransTree(sc.prettyobj):
    '''
    A class for holding a transmission tree. Sources and targets are both lists
    of the same length as the population size. Sources has one entry for people who
    have been infected, zero for those who haven't. Targets is a list of lists,
    with the length of the list being the number of people that person infected.

    Args:
        sources (list): the person who infected this person
        targets (list): the people this person infected
    '''

    def __init__(self, pop_size=None, sources=None, targets=None):

        # Handle inputs and preallocate if a size is given
        if sources is None:
            if pop_size is None:
                sources = []
            else:
                sources = [None]*pop_size
        if targets is None:
            if pop_size is None:
                targets = []
            else:
                targets = [[] for p in range(pop_size)] # Make a list of empty lists

        # Assign
        self.sources = sources
        self.targets = targets
        return


    def plot(self):
        raise NotImplementedError('Transmission tree plotting is not yet available')