"""
Inventory: tracks items, keys, hearts, and triforce pieces collected during validation.
"""

from zora.data_model import Direction, Item


class Inventory:
    def __init__(self, progressive_items: bool = False) -> None:
        self.progressive_items = progressive_items
        self.items: set[Item]
        self.item_locations: set[tuple[int, int]]   # (level_num_or_cave_id, room_or_pos)
        self.locations_where_keys_were_used: set[tuple[int, int, Direction]]
        self.num_heart_containers: int
        self.num_keys: int
        self.levels_with_triforce_obtained: list[int]
        self.still_making_progress_bit: bool
        self.reset()

    def reset(self) -> None:
        self.items = set()
        self.item_locations = set()
        self.locations_where_keys_were_used = set()
        self.num_heart_containers = 3
        self.num_keys = 0
        self.levels_with_triforce_obtained = []
        self.still_making_progress_bit = False

    def set_still_making_progress_bit(self) -> None:
        self.still_making_progress_bit = True

    def clear_making_progress_bit(self) -> None:
        self.still_making_progress_bit = False

    def still_making_progress(self) -> bool:
        return self.still_making_progress_bit

    def add_item(self, item: Item, location_key: tuple[int, int] | None = None) -> None:
        """Add an item to inventory.

        Items that are never meaningful for logic are silently ignored.
        location_key is an opaque (a, b) tuple used to deduplicate pickups
        from the same location. Pass None for virtual/hint items.
        """
        if item in (
            Item.OVERWORLD_NO_ITEM, Item.MAP, Item.COMPASS, Item.MAGICAL_SHIELD,
            Item.BOMBS, Item.FIVE_RUPEES, Item.NOTHING, Item.SINGLE_HEART,
            Item.TRIFORCE_OF_POWER,
        ):
            return

        # KEY items are consumable and re-collectable each iteration.
        if item == Item.KEY:
            self.num_keys += 1
            return

        # Deduplicate all other items by location_key or item identity.
        # In progressive mode, base items are intentionally collected multiple times
        # to trigger upgrade chains — only deduplicate by location, not by identity.
        _progressive_base = (
            self.progressive_items and item in (
                Item.WOOD_SWORD, Item.BLUE_RING, Item.WOOD_ARROWS, Item.BLUE_CANDLE,
            )
        )
        if item == Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM:
            if item in self.items:
                return
            # fall through to add it
        elif location_key is not None:
            if location_key in self.item_locations:
                return
            self.item_locations.add(location_key)
        elif not _progressive_base:
            if item in self.items:
                return

        self.set_still_making_progress_bit()

        if item == Item.HEART_CONTAINER:
            self.num_heart_containers += 1
            return

        if item == Item.TRIFORCE:
            assert location_key is not None, "TRIFORCE must always be collected with a location_key"
            level_num = location_key[0]
            if level_num not in self.levels_with_triforce_obtained:
                self.levels_with_triforce_obtained.append(level_num)
            return

        # Upgrade chains: simulate progressive item stacking.
        # Only applies when progressive_items mode is on.
        # Check existing inventory BEFORE adding, since the check tests
        # whether we already own a copy.
        if self.progressive_items:
            if item == Item.WOOD_SWORD and Item.WHITE_SWORD in self.items:
                self.items.add(Item.MAGICAL_SWORD)
            elif item == Item.WOOD_SWORD and Item.WOOD_SWORD in self.items:
                self.items.add(Item.WHITE_SWORD)
            elif item == Item.BLUE_RING and Item.BLUE_RING in self.items:
                self.items.add(Item.RED_RING)
            elif item == Item.BLUE_CANDLE and Item.BLUE_CANDLE in self.items:
                self.items.add(Item.RED_CANDLE)
            elif item == Item.WOOD_ARROWS and Item.WOOD_ARROWS in self.items:
                self.items.add(Item.SILVER_ARROWS)

        self.items.add(item)

    def get_heart_count(self) -> int:
        return self.num_heart_containers

    def get_triforce_count(self) -> int:
        return len(self.levels_with_triforce_obtained)

    def has_key(self) -> bool:
        return self.has(Item.MAGICAL_KEY) or self.num_keys > 0

    def use_key(self, level_num: int, room_num: int, exit_direction: Direction) -> None:
        assert self.has_key()
        if self.has(Item.MAGICAL_KEY):
            return
        key = (level_num, room_num, exit_direction)
        if key in self.locations_where_keys_were_used:
            return
        self.num_keys -= 1
        self.locations_where_keys_were_used.add(key)

    def has(self, item: Item) -> bool:
        return item in self.items

    def has_sword(self) -> bool:
        return (Item.WOOD_SWORD in self.items
                or Item.WHITE_SWORD in self.items
                or Item.MAGICAL_SWORD in self.items)

    def has_sword_or_wand(self) -> bool:
        return self.has_sword() or Item.WAND in self.items

    def has_reusable_weapon(self) -> bool:
        return self.has_sword_or_wand() or Item.RED_CANDLE in self.items

    def has_reusable_weapon_or_boomerang(self) -> bool:
        return self.has_reusable_weapon() or self._has_boomerang()

    def has_recorder_and_reusable_weapon(self) -> bool:
        return Item.RECORDER in self.items and self.has_reusable_weapon()

    def has_bow_and_arrows(self) -> bool:
        return (Item.BOW in self.items
                and (Item.WOOD_ARROWS in self.items or Item.SILVER_ARROWS in self.items))

    def has_bow_silver_arrows_and_sword(self) -> bool:
        return self.has_sword() and Item.BOW in self.items and Item.SILVER_ARROWS in self.items

    def has_candle(self) -> bool:
        return Item.BLUE_CANDLE in self.items or Item.RED_CANDLE in self.items

    def has_ring(self) -> bool:
        return Item.BLUE_RING in self.items or Item.RED_RING in self.items

    def _has_boomerang(self) -> bool:
        return Item.WOOD_BOOMERANG in self.items or Item.MAGICAL_BOOMERANG in self.items

    def to_string(self) -> str:
        return ", ".join(item.name for item in sorted(self.items, key=lambda i: i.value))
