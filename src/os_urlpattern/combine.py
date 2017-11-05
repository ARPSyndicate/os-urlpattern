from pattern import get_pattern_from_cache
from url_meta import URLMeta
from piece_pattern_tree import PiecePatternTree
from piece_pattern_agent import BasePiecePattern, MixedPiecePattern, LastDotSplitPiecePattern


class _Bag(object):
    def __init__(self):
        self._objs = []
        self._count = 0

    def get_inner_obj(self):
        obj = self._objs[0]
        while isinstance(obj, _Bag):
            obj = obj.objs[0]
        return obj

    @property
    def objs(self):
        return self._objs

    @property
    def num(self):
        return len(self._objs)

    def add(self, obj):
        self._objs.append(obj)
        self._count += obj.count

    @property
    def count(self):
        return self._count

    def set_pattern(self, pattern):
        change = False
        for obj in self._objs:
            if obj.set_pattern(pattern):
                change = True
        return change


class Combiner(object):
    def __init__(self, config, meta_info, **kwargs):
        self._meta_info = meta_info
        self._config = config
        self._min_combine_num = self.config.getint(
            'make', 'min_combine_num')

    @property
    def meta_info(self):
        return self._meta_info

    @property
    def config(self):
        return self._config

    def add_bag(self, bag):
        pass

    def combine(self):
        pass


class LengthCombiner(Combiner):
    def __init__(self, config, meta_info, **kwargs):
        super(LengthCombiner, self).__init__(config, meta_info, **kwargs)
        self._length_bags = {}
        self._force_combine = kwargs.get('force_combine', False)

    def add_bag(self, bag):
        length = bag.objs[0].piece_pattern.piece_length
        if length not in self._length_bags:
            self._length_bags[length] = _Bag()
        self._length_bags[length].add(bag)

    def _set_pattern(self, length_bags, use_base=False):
        only_one = len(length_bags) == 1
        for length, bag in length_bags.iteritems():
            pattern = None
            if use_base and not only_one:
                pattern = bag.get_inner_obj().piece_pattern.base_pattern
            else:
                pattern = bag.get_inner_obj().piece_pattern.exact_num_pattern(
                    length)
            bag.set_pattern(pattern)

    def combine(self):
        if self._force_combine:
            self._set_pattern(self._length_bags, use_base=True)
        else:
            length_keep = {}
            length_unknow = {}
            _num = 0
            for length, bag in self._length_bags.iteritems():
                if bag.num >= self._min_combine_num:
                    length_keep[length] = bag
                else:
                    length_unknow[length] = bag
                    _num += bag.num

            self._set_pattern(length_keep)
            if _num >= self._min_combine_num:
                self._set_pattern(length_unknow, use_base=True)


class LastDotSplitFuzzyPatternCombiner(Combiner):
    def __init__(self, config, meta_info, **kwargs):
        super(LastDotSplitFuzzyPatternCombiner, self).__init__(
            config, meta_info, **kwargs)
        self._combiners = {}

    def add_bag(self, bag):
        piece_pattern = LastDotSplitPiecePattern(
            bag.get_inner_obj().piece_pattern)
        if piece_pattern.part_num <= 1:
            return
        h = hash(piece_pattern.pattern)
        if h not in self._combiners:
            self._combiners[h] = MultiLevelCombiner(
                self.config, self.meta_info, part_num=piece_pattern.part_num,
                pp_agent_class=LastDotSplitPiecePattern)
        self._combiners[h].add_bag(bag)

    def combine(self):
        for combiner in self._combiners.itervalues():
            combiner.combine()


class MixedPatternCombiner(Combiner):
    def __init__(self, config, meta_info, **kwargs):
        super(MixedPatternCombiner, self).__init__(config, meta_info, **kwargs)
        self._mixed_pattern_bags = {}

    def add_bag(self, bag):
        h = hash(bag.get_inner_obj().piece_pattern.mixed_pattern)
        if h not in self._mixed_pattern_bags:
            self._mixed_pattern_bags[h] = _Bag()
        self._mixed_pattern_bags[h].add(bag)

    def _combine_mixed_pattern(self, pattern_bag_dict):
        for pattern_bag in pattern_bag_dict.itervalues():
            self._combine_mixed_pattern_bag(pattern_bag)

    def _combine_mixed_pattern_bag(self, pattern_bag, force_combine=False):
        pp_agent_class = MixedPiecePattern
        piece_pattern = pp_agent_class(
            pattern_bag.get_inner_obj().piece_pattern)
        combiner = MultiLevelCombiner(
            self.config, self.meta_info,
            part_num=piece_pattern.part_num, force_combine=force_combine,
            pp_agent_class=pp_agent_class)
        for piece_bag in pattern_bag.objs:
            combiner.add_bag(piece_bag)
        combiner.combine()

    def _combine_fuzzy_pattern_with_last_dot_split(self, pattern_bag_dict):
        combiner = LastDotSplitFuzzyPatternCombiner(
            self.config, self.meta_info)
        for pattern_bag in pattern_bag_dict.itervalues():
            for piece_bag in pattern_bag.objs:
                combiner.add_bag(piece_bag)
        combiner.combine()

    def _combine_fuzzy_pattern(self, pattern_bag_dict):
        if self.meta_info.is_last_path_level():
            self._combine_fuzzy_pattern_with_last_dot_split(pattern_bag_dict)
        _bag = _Bag()
        for pattern_bag in pattern_bag_dict.itervalues():
            for piece_bag in pattern_bag.objs:
                if piece_bag.get_inner_obj().piece_eq_pattern():
                    _bag.add(piece_bag)
        if _bag.num >= self._min_combine_num:
            _bag.set_pattern(_bag.get_inner_obj().piece_pattern.fuzzy_pattern)

    def combine(self):
        low_prob = {}
        high_prob = {}
        _num = 0
        for h, bag in self._mixed_pattern_bags.iteritems():
            if bag.num >= self._min_combine_num:
                high_prob[h] = bag
            else:
                low_prob[h] = bag
                _num += bag.num

        self._combine_mixed_pattern(high_prob)
        for h, pattern_bag in high_prob.iteritems():
            bag = _Bag()
            for piece_bag in pattern_bag.objs:
                if piece_bag.get_inner_obj().piece_eq_pattern():
                    bag.add(piece_bag)
            if bag.num > 0:
                if bag.num < self._min_combine_num:
                    low_prob[h] = bag
                    _num += bag.num
                else:
                    self._combine_mixed_pattern_bag(bag, True)
        if len(low_prob) > 1 and _num >= self._min_combine_num:
            self._combine_fuzzy_pattern(low_prob)


class BasePatternCombiner(Combiner):
    def __init__(self, config, meta_info, **kwargs):
        super(BasePatternCombiner, self).__init__(config, meta_info, ** kwargs)
        self._base_pattern_bags = {}

    def add_bag(self, bag):
        h = hash(bag.get_inner_obj().piece_pattern.base_pattern)
        if h not in self._base_pattern_bags:
            self._base_pattern_bags[h] = _Bag()
        self._base_pattern_bags[h].add(bag)

    def _combine_base_pattern(self, pattern_bag_dict):
        for pattern_bag in pattern_bag_dict.itervalues():
            self._combine_base_pattern_bag(pattern_bag)

    def _combine_base_pattern_bag(self, pattern_bag, force_combine=False):
        pp_agent_class = BasePiecePattern
        piece_pattern = pp_agent_class(
            pattern_bag.get_inner_obj().piece_pattern)
        combiner = MultiLevelCombiner(
            self.config, self.meta_info,
            part_num=piece_pattern.part_num, force_combine=force_combine,
            pp_agent_class=pp_agent_class)
        for piece_bag in pattern_bag.objs:
            combiner.add_bag(piece_bag)
        combiner.combine()

    def _combine_mixed_pattern(self, pattern_bag_dict):
        combiner = MixedPatternCombiner(self.config, self.meta_info)
        for pattern_bag in pattern_bag_dict.itervalues():
            for piece_bag in pattern_bag.objs:
                combiner.add_bag(piece_bag)
        combiner.combine()

    def combine(self):
        low_prob = {}
        high_prob = {}
        _num = 0
        for h, bag in self._base_pattern_bags.iteritems():
            if bag.num >= self._min_combine_num:
                high_prob[h] = bag
            else:
                low_prob[h] = bag
                _num += bag.num
        self._combine_base_pattern(high_prob)
        for h, pattern_bag in high_prob.iteritems():
            bag = _Bag()
            for piece_bag in pattern_bag.objs:
                if piece_bag.get_inner_obj().piece_eq_pattern():
                    bag.add(piece_bag)
            if bag.num > 0:
                if bag.num < self._min_combine_num:
                    low_prob[h] = bag
                    _num += bag.num
                else:
                    self._combine_base_pattern_bag(bag, True)

        if len(low_prob) > 1 and _num >= self._min_combine_num:
            self._combine_mixed_pattern(low_prob)


class MultiLevelCombiner(Combiner):
    def __init__(self, config, meta_info, **kwargs):
        super(MultiLevelCombiner, self).__init__(config, meta_info, **kwargs)
        self._kwargs = kwargs
        self._url_meta = URLMeta(self._kwargs.pop('part_num'), [], False)
        self._piece_pattern_tree = PiecePatternTree()
        self._piece_bags = []
        self._pp_agent_class = self._kwargs.pop('pp_agent_class')

    def add_bag(self, bag):
        self._piece_bags.append(bag)
        for node in bag.objs:
            pps = self._pp_agent_class(node.piece_pattern).piece_patterns
            self._piece_pattern_tree.add_piece_patterns(
                pps, node.count, False)

    def combine(self):
        combine(self.config, self._url_meta,
                self._piece_pattern_tree, **self._kwargs)
        piece_pattern_dict = {}
        pattern_counter = {}
        for path in self._piece_pattern_tree.dump_paths():
            piece = ''.join([node.piece for node in path])
            pattern = get_pattern_from_cache(
                ''.join([str(node.pattern) for node in path]))
            piece_pattern_dict[piece] = pattern
            if pattern not in pattern_counter:
                pattern_counter[pattern] = 0
            pattern_counter[pattern] += 1
        for piece_bag in self._piece_bags:
            node = piece_bag.get_inner_obj()
            if node.piece in piece_pattern_dict:
                pattern = piece_pattern_dict[node.piece]
                if pattern in pattern_counter and pattern_counter[pattern] >= self._min_combine_num:
                    piece_bag.set_pattern(pattern)


class MetaInfo(object):
    def __init__(self, url_meta, current_level):
        self._url_meta = url_meta
        self._current_level = current_level

    @property
    def current_level(self):
        return self._current_level

    @property
    def url_meta(self):
        return self._url_meta

    def is_last_level(self):
        return self.url_meta.depth == self._current_level

    def is_last_path_level(self):
        return self.url_meta.path_depth == self._current_level

    def get_next_level_meta_info(self):
        return MetaInfo(self.url_meta, self._current_level + 1)


class CombinePredictor(object):
    def __init__(self, combine_processor):
        self._combine_processor = combine_processor
        self._min_combine_num = combine_processor.config.getint(
            'make', 'min_combine_num')
        self._count_cluster = {}

    def _get_next_level_processor(self, base_processor):
        return CombineProcessor(
            base_processor.config,
            base_processor.meta_info.get_next_level_meta_info(),
            use_predictor=False)

    def preprocess(self):
        if self._combine_processor.meta_info.is_last_level() \
                or len(self._combine_processor._piece_node_bag) < self._min_combine_num:
            return
        p_processor = self._combine_processor
        n_processor = self._get_next_level_processor(p_processor)
        count = 0
        while not p_processor.meta_info.is_last_level():
            count += 1
            for node in p_processor.nodes():
                for child in node.children:
                    n_processor.add_node(child)
            if len(n_processor._piece_node_bag) < self._min_combine_num:
                p_processor = n_processor
                n_processor = self._get_next_level_processor(p_processor)
            else:
                break
        n_processor.combine()

        pattern_cluster = {}
        for node in n_processor.nodes():
            pattern = node.pattern
            if pattern not in pattern_cluster:
                pattern_cluster[pattern] = set()
            parrent = node.get_parrent(count)
            pattern_cluster[pattern].add(parrent)
            self._count_cluster[parrent.piece] = pattern_cluster[pattern]
        for p in self._count_cluster:
            self._count_cluster[p] = len(self._count_cluster[p])

    def skip_combine(self, bag):
        piece = bag.objs[0].piece_pattern.piece
        if bag.count >= self._min_combine_num \
                and self._count_cluster.get(piece, 0) < self._min_combine_num:
            return True
        return False


class CombineProcessor(object):
    def __init__(self, config, meta_info, **kwargs):
        self._config = config
        self._min_combine_num = self.config.getint('make', 'min_combine_num')
        self._meta_info = meta_info
        self._piece_node_bag = {}
        self._combiner_class = None
        self._kwargs = kwargs
        self._force_combine = kwargs.get('force_combine', False)

    def nodes(self):
        for bag in self._piece_node_bag.itervalues():
            for node in bag.objs:
                yield node

    @property
    def meta_info(self):
        return self._meta_info

    @property
    def config(self):
        return self._config

    def add_node(self, node):
        piece = node.piece_pattern.piece
        if piece not in self._piece_node_bag:
            self._piece_node_bag[piece] = _Bag()
        self._piece_node_bag[piece].add(node)

    def _get_combiner_class(self):
        combine_class = LengthCombiner
        for bag in self._piece_node_bag.itervalues():
            node = bag.get_inner_obj()
            if node.piece_pattern.base_part_num > 1:
                combine_class = BasePatternCombiner
            return combine_class

    def combine(self):
        if len(self._piece_node_bag) <= 1:
            return
        combine_predictor = CombinePredictor(self)
        if self._kwargs.get('use_predictor', True):
            combine_predictor.preprocess()
        else:
            self._kwargs.pop('use_predictor')

        combiner_class = self._get_combiner_class()
        combiner = combiner_class(self.config, self.meta_info, **self._kwargs)

        for bag in self._piece_node_bag.itervalues():
            if self._force_combine or not combine_predictor.skip_combine(bag):
                combiner.add_bag(bag)
        combiner.combine()

    def process(self):
        self.combine()
        if self.meta_info.is_last_level():
            return
        next_level_processors = {}
        for node in self.nodes():
            n_hash = hash(node.pattern)
            if n_hash not in next_level_processors:
                next_level_processors[n_hash] = CombineProcessor(
                    self.config, self.meta_info.get_next_level_meta_info(), **self._kwargs)
            for child in node.children:
                next_level_processors[n_hash].add_node(child)
        for processor in next_level_processors.itervalues():
            processor.process()


def combine(config, url_meta, piece_pattern_tree, **kwargs):
    meta_info = MetaInfo(url_meta, 0)
    processor = CombineProcessor(config, meta_info, **kwargs)
    processor.add_node(piece_pattern_tree.root)
    processor.process()
