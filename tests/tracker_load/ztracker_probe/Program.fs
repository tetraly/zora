// ZTracker data-level load check: reads a save the way ZTracker's loader does for its overworld tiles and item boxes
// (Z1R_WPF/WPFUI.fs, "poke loaded data values"), using ZTracker's own SaveAndLoad classes and TrackerModel, and prints
// what each tile and box ended up holding as JSON. Usage: ZTrackerProbe <save file>
module ZTrackerProbe

open System
open System.IO
open System.Text.Json

let opts = JsonSerializerOptions(AllowTrailingCommas = true)

[<EntryPoint>]
let main argv =
    let json = File.ReadAllText argv.[0]
    let root = JsonDocument.Parse(json, JsonDocumentOptions(AllowTrailingCommas = true)).RootElement
    let out = Collections.Generic.Dictionary<string, obj>()
    try
        let version = (match root.TryGetProperty "Version" with | true, v -> v.GetString() | _ -> "")
        out.["version"] <- box version
        let ow = JsonSerializer.Deserialize<SaveAndLoad.Overworld>(root.GetProperty("Overworld").GetRawText(), opts)
        let items = JsonSerializer.Deserialize<SaveAndLoad.Items>(root.GetProperty("Items").GetRawText(), opts)
        let quest =
            match ow.Quest with
            | 0 -> OverworldData.OWQuest.FIRST | 1 -> OverworldData.OWQuest.SECOND | 2 -> OverworldData.OWQuest.MIXED_FIRST
            | 3 -> OverworldData.OWQuest.MIXED_SECOND | 4 -> OverworldData.OWQuest.BLANK | _ -> failwith "bad load data at root.Overworld.Quest"
        let kind = if items.HiddenDungeonNumbers then TrackerModel.DungeonTrackerInstanceKind.HIDE_DUNGEON_NUMBERS else TrackerModel.DungeonTrackerInstanceKind.DEFAULT
        TrackerModel.initializeAll(OverworldData.OverworldInstance(quest), kind)
        if ow.Map.Length <> 16 * 8 * 3 then failwith "bad load data at data.Overworld.Map"
        // tiles
        let tiles = ResizeArray<obj>()
        for j = 0 to 7 do
            for i = 0 to 15 do
                let cur = ow.Map.[j*16*3 + i*3]
                let ok = TrackerModel.overworldMapMarks.[i,j].AttemptToSet(cur)
                let got = TrackerModel.overworldMapMarks.[i,j].Current()
                if not ok || got <> cur then tiles.Add(box {| column = i; row = j; requested = cur; got = got; accepted = ok |})
        out.["tilesNotKept"] <- box tiles
        // boxes
        let boxes = ResizeArray<obj>()
        let apply (name: string) (src: SaveAndLoad.Box) (dest: TrackerModel.Box) =
            if not (isNull src) then
                let ok = src.TryApply(dest)
                // (why it was refused, from the same call without the try: ZTracker's own message)
                let why = if ok then "" else (try dest.Set(src.CellCurrent, TrackerModel.PlayerHas.FromInt src.PlayerHas); "" with e -> e.Message)
                boxes.Add(box {| name = name; requested = src.CellCurrent; got = dest.CellCurrent(); accepted = ok; why = why |})
        apply "WoodSwordBox" items.WoodSwordBox TrackerModel.sword1Box
        apply "WhiteSwordBox" items.WhiteSwordBox TrackerModel.sword2Box
        apply "MagicalSwordBox" items.MagicalSwordBox TrackerModel.sword3Box
        apply "LadderBox" items.LadderBox TrackerModel.ladderBox
        apply "ArmosBox" items.ArmosBox TrackerModel.armosBox
        apply "LetterBox" items.LetterBox TrackerModel.letterBox
        for i = 0 to 8 do
            let ds = items.Dungeons.[i]
            let dd = TrackerModel.GetDungeon(i)
            if ds.Boxes.Length <> dd.Boxes.Length then failwithf "dungeon %d: the file has %d boxes, ZTracker has %d" (i+1) ds.Boxes.Length dd.Boxes.Length
            for k = 0 to ds.Boxes.Length - 1 do
                apply (sprintf "Level%dBox%d" (i+1) (k+1)) ds.Boxes.[k] dd.Boxes.[k]
        out.["boxes"] <- box boxes
        out.["error"] <- null
    with e -> out.["error"] <- box (e.GetType().Name + ": " + e.Message)
    printfn "%s" (JsonSerializer.Serialize(out))
    0
