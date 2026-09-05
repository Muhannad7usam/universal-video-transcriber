def select_indices(count:int, *, all_items=False, video=None, range_=None, first=None):
    if count<0: raise ValueError("Invalid item count.")
    if all_items: return list(range(1,count+1))
    if video is not None:
        if not 1<=video<=count: raise ValueError("Video number is out of range.")
        return [video]
    if range_ is not None:
        a,b=range_
        if a<1 or b<a or b>count: raise ValueError("Playlist range is out of range.")
        return list(range(a,b+1))
    if first is not None:
        if first<1: raise ValueError("First N must be positive.")
        return list(range(1,min(first,count)+1))
    return []
