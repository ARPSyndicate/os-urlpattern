from collections import Counter, OrderedDict, defaultdict
from types import MethodType

from .compat import iteritems, itervalues
from .definition import DIGIT_AND_ASCII_RULE_SET, BasePatternRule
from .node_viewer import BaseViewer, LengthViewer, MixedViewer, PieceViewer
from .parse_utils import URLMeta, number_rule, wildcard_rule
from .pattern import Pattern
from .piece_pattern_tree import PiecePatternNode, PiecePatternTree
from .utils import Bag


class TBag(Bag):
    def __init__(self):
        super(TBag, self).__init__()
        self._count = 0

    @property
    def count(self):
        return self._count

    def add(self, obj):
        super(TBag, self).add(obj)
        self._count += obj.count

    def set_pattern(self, pattern):
        for obj in self:
            obj.set_pattern(pattern)


class PieceBag(TBag):
    def __init__(self):
        super(PieceBag, self).__init__()
        self._p_counter = Counter()

    def incr(self, incr):
        self._count += incr

    def add(self, piece_node):
        super(PieceBag, self).add(piece_node)
        p = piece_node.parrent
        if p is not None:
            self._p_counter[p.parsed_piece] += piece_node.count

    @property
    def p_counter(self):
        return self._p_counter


class PieceBucket(TBag):
    def __init__(self):
        super(PieceBucket, self).__init__()
        self._objs = {}

    def add(self, piece_pattern_node):
        piece = piece_pattern_node.piece
        if piece not in self._objs:
            self._objs[piece] = PieceBag()
        self._objs[piece].add(piece_pattern_node)
        self._count += piece_pattern_node.count

    def __getitem__(self, key):
        return self._objs[key]

    def __contains__(self, key):
        return key in self._objs

    def _get(self):
        for obj in itervalues(self._objs):
            return obj

    def __iter__(self):
        return itervalues(self._objs)


class LengthPieceBucket(PieceBucket):

    def __init__(self):
        super(LengthPieceBucket, self).__init__()
        self._p_counter = None

    @property
    def p_counter(self):
        if self._p_counter is None:
            self._p_counter = Counter()
            for p in self:
                self._p_counter.update(p.p_counter)
        return self._p_counter

    def add(self, piece_bag):
        piece = piece_bag.pick().piece
        if piece in self._objs:
            raise ValueError('duplicated')
        self._objs[piece] = piece_bag
        self._count += piece_bag.count


def confused(total, part, threshold):
    if total < threshold:
        return False
    o_part = total - part
    if part >= threshold and o_part >= threshold:
        return True
    return abs(part - o_part) < threshold - 1


class PatternCluster(object):
    def __init__(self, processor):
        self._processor = processor
        self._min_cluster_num = processor.config.getint(
            'make', 'min_cluster_num')

    def get_processor(self, n):
        processor = self._processor
        while n > 0 and processor is not None:
            processor = processor.pre_level_processor
            n -= 1
        return processor

    @property
    def pre_level_processor(self):
        return self._processor.pre_level_processor

    def as_cluster(self, p_counter):
        return False

    def cluster(self):
        pass

    def add(self, obj):
        pass


class PiecePatternCluster(PatternCluster):
    def __init__(self, processor):
        super(PiecePatternCluster, self).__init__(processor)
        self._piece_bucket = PieceBucket()
        self._piece_skip = defaultdict(lambda: False)

    def revise(self, p_counter):
        for parsed_piece, count in iteritems(p_counter):
            self._piece_bucket[parsed_piece.piece].incr(0 - count)

    def as_cluster(self, p_counter):
        if len(p_counter) >= self._min_cluster_num:
            return False
        total = sum([self._piece_bucket[p.piece].count for p in p_counter])
        max_count = p_counter.most_common(1)[0][1]
        return not confused(total, max_count, self._min_cluster_num)

    def iter_nodes(self):
        return self._piece_bucket.iter_all()

    def add(self, piece_pattern_node):
        piece = piece_pattern_node.piece
        self._piece_bucket.add(piece_pattern_node)
        bag = self._piece_bucket[piece]
        if self._piece_skip[piece] or bag.count < self._min_cluster_num:
            return

        p_node = piece_pattern_node.parrent
        if p_node is None or p_node.children_num == 1:
            return

        if p_node.count - piece_pattern_node.count >= self._min_cluster_num:
            self._piece_skip[piece] = True
            return

        for b_node in p_node.iter_children():
            b_piece = b_node.piece
            if b_piece == piece or b_piece not in self._piece_bucket:
                continue
            b_bag = self._piece_bucket[b_piece]
            if b_bag.count >= self._min_cluster_num:
                self._piece_skip[b_piece] = True
                self._piece_skip[piece] = True
                break

    def _get_forward_cluster(self):
        cluster_cls = LengthPatternCluster
        piece_pattern_node = self._piece_bucket.pick()
        if len(piece_pattern_node.parsed_piece.pieces) > 1:
            cluster_cls = BasePatternCluster
        return self._processor.get_cluster(cluster_cls)

    def cluster(self):
        if len(self._piece_bucket) < self._min_cluster_num:
            if self._piece_bucket.count < self._min_cluster_num:
                return
            max_count = max(self._piece_bucket, key=lambda x: x.count).count
            if not confused(self._piece_bucket.count, max_count, self._min_cluster_num):
                return

        forward_cluster = self._get_forward_cluster()

        for piece_bag in self._piece_bucket:
            piece = piece_bag.pick().piece
            if self._piece_skip[piece] \
                    or piece_bag.count < self._min_cluster_num \
                    or not self.get_processor(1).seek_cluster(piece_bag.p_counter):
                forward_cluster.add(piece_bag)
            else:
                self.get_processor(1).revise(piece_bag.p_counter)


class LengthPatternCluster(PatternCluster):
    def __init__(self, processor):
        super(LengthPatternCluster, self).__init__(processor)
        self._length_buckets = {}

    def as_cluster(self, p_counter):
        print '================', p_counter
        return False
        total = sum([self._length_buckets[p.piece_length]
                     [p.piece].count for p in p_counter])

        max_count = 0
        total_count = 0
        for length in lengths:
            length_bag = self._length_bags[length]
            if length_bag.count > max_count:
                max_count = length_bag.count
            total_count += length_bag.count

        return not confused(total_count, max_count, self._min_cluster_num)

    def add(self, piece_bag):
        piece_length = piece_bag.pick().parsed_piece.piece_length
        if piece_length not in self._length_buckets:
            self._length_buckets[piece_length] = LengthPieceBucket()
        self._length_buckets[piece_length].add(piece_bag)

    def _length_as_cluster(self, length_bucket):
        if len(length_bucket) < self._min_cluster_num:
            if length_bucket.count < self._min_cluster_num:
                return False
            max_count = max(length_bucket, key=lambda x: x.count).count
            if not confused(length_bucket.count, max_count, self._min_cluster_num):
                return False

        return True

    def cluster(self):
        if len(self._length_buckets) < self._min_cluster_num:
            total = sum([c.count for c in itervalues(self._length_buckets)])
            if total < self._min_cluster_num:
                return
            max_bucket = max(itervalues(self._length_buckets),
                             key=lambda x: x.count)
            if not confused(total, max_bucket.count, self._min_cluster_num):
                if self._length_as_cluster(max_bucket):
                    self._set_pattern(max_bucket)
                    return

        forward_cluster = self._processor.get_cluster(FuzzyPatternCluster)
        for length_bucket in itervalues(self._length_buckets):
            if not self._length_as_cluster(length_bucket) \
                    or not self.get_processor(1).seek_cluster(length_bucket.p_counter):
                forward_cluster.add(length_bucket)
            else:
                self._set_pattern(length_bucket)
                self.get_processor(1).revise(length_bucket.p_counter)

    def _set_pattern(self, length_bucket):
        parsed_piece = length_bucket.pick().parsed_piece
        length = parsed_piece.piece_length
        pattern = Pattern(number_rule(parsed_piece.fuzzy_rule, length))
        length_bucket.set_pattern(pattern)


class MultiPartPatternCluster(PatternCluster):
    pass


class BasePatternCluster(MultiPartPatternCluster):
    def __init__(self, processor):
        super(BasePatternCluster, self).__init__(processor)

    def add(self, piece_bag):
        pass


class MixedPatternCluster(MultiPartPatternCluster):
    def __init__(self, processor):
        super(MixedPatternCluster, self).__init__(processor)

    def add(self, piece_bag):
        pass


class LastDotSplitFuzzyPatternCluster(MultiPartPatternCluster):
    def __init__(self, processor):
        super(LastDotSplitFuzzyPatternCluster, self).__init__(processor)

    def add(self, piece_bag):
        pass


class FuzzyPatternCluster(PatternCluster):
    def __init__(self, processor):
        super(FuzzyPatternCluster, self).__init__(processor)
        self._cached_bag = TBag()
        self._force_pattern = False
        self._fuzzy_pattern = None
        self._mc_bag = None

    def add(self, bag):
        if self._force_pattern:
            self._set_pattern(bag)
        else:
            self._cached_bag.add(bag)
            if self._mc_bag is None or bag.count > self._mc_bag.count:
                self._mc_bag = bag
            if len(self._cached_bag) >= self._min_cluster_num:
                self._force_pattern = True

    def cluster(self):
        cbc = self._cached_bag.count
        if cbc <= 0:
            return
        mcn = self._min_cluster_num
        mbc = self._mc_bag.count
        if self._force_pattern \
            or (len(self._cached_bag) > 1
                and cbc >= mcn
                and (mbc < mcn
                     or cbc - mbc >= mcn
                     or 2 * mbc - cbc < mcn - 1)):
            self._set_pattern(self._cached_bag)

    def _set_pattern(self, bag):
        if self._fuzzy_pattern is None:
            self._fuzzy_pattern = Pattern(
                wildcard_rule(bag.pick().parsed_piece.fuzzy_rule))
        bag.set_pattern(self._fuzzy_pattern)


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

    def is_last_path(self):
        return self.url_meta.path_depth == self._current_level

    def next_level_meta_info(self):
        return MetaInfo(self.url_meta, self.current_level + 1)


CLUSTER_CLASSES = [PiecePatternCluster, BasePatternCluster, MixedPatternCluster,
                   LastDotSplitFuzzyPatternCluster, LengthPatternCluster,
                   FuzzyPatternCluster]


class ClusterProcessor(object):
    def __init__(self, config, meta_info, pre_level_processor):
        self._config = config
        self._meta_info = meta_info
        self._pattern_clusters = OrderedDict(
            [(c.__name__, c(self)) for c in CLUSTER_CLASSES])
        self._pre_level_processor = pre_level_processor

    def seek_cluster(self, p_counter):
        for c in self._pattern_clusters.itervalues():
            if c.as_cluster(p_counter):
                return True

        return False

    def revise(self, p_counter):
        self.get_cluster(PiecePatternCluster).revise(p_counter)

    def get_cluster(self, cluster_cls):
        return self._pattern_clusters[cluster_cls.__name__]

    @property
    def meta_info(self):
        return self._meta_info

    @property
    def config(self):
        return self._config

    @property
    def pre_level_processor(self):
        return self._pre_level_processor

    def _process(self, ):
        for c in self._pattern_clusters.itervalues():
            c.cluster()

    def process(self):
        self._process()
        if self._meta_info.is_last_level():
            return

        next_level_processors = self._create_next_level_processors()

        for processor in itervalues(next_level_processors):
            processor.process()

    def _create_next_level_processors(self):
        pp_cluster = self.get_cluster(PiecePatternCluster)
        next_level_processors = {}

        for node in pp_cluster.iter_nodes():
            pattern = node.pattern
            if pattern not in next_level_processors:
                next_level_processors[pattern] = self._create_next_level_processor(
                )
            next_level_processor = next_level_processors[pattern]
            next_pp_cluster = next_level_processor.get_cluster(
                PiecePatternCluster)
            for child in node.iter_children():
                next_pp_cluster.add(child)

        return next_level_processors

    def _create_next_level_processor(self):
        return ClusterProcessor(self._config,
                                self._meta_info.next_level_meta_info(),
                                self)


def split(piece_pattern_tree):
    yield


def process(config, url_meta, piece_pattern_tree, **kwargs):
    meta_info = MetaInfo(url_meta, 0)
    processor = ClusterProcessor(config, meta_info, None)
    processor.get_cluster(PiecePatternCluster).add(piece_pattern_tree.root)
    processor.process()


def cluster(config, url_meta, piece_pattern_tree, **kwargs):
    process(config, url_meta, piece_pattern_tree, **kwargs)

    return
    for sub_piece_pattern_tree in split(piece_pattern_tree):
        process(config, url_meta, sub_piece_pattern_tree)
