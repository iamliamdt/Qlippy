"""Everything Qlippy says.

Texts are keyed by Help/Harass level (0 Helpful .. 3 Unhinged). A missing
level falls back to the nearest lower one. Placeholders use str.format
names; values are HTML-escaped before insertion.
"""

import datetime
import html
import random

# --------------------------------------------------------------------- rules
# min_level: lowest level at which the rule fires
# cooldown:  seconds before the same rule may fire again
# group:     rules sharing a group share the cooldown
# anim:      animation played while talking
RULES = {
    # ---------------------------------------------------------------- help
    "crs_mismatch": {
        "min_level": 0, "cooldown": 300, "anim": "tap_map", "title": "CRS mismatch",
        "texts": {
            0: ["'{name}' is in {layer_crs}, but the project is in {project_crs}. QGIS reprojects it for "
                "display, but Processing tools use each layer's own CRS. Reproject Layer (Processing "
                "Toolbox) makes them match."],
            1: ["'{name}' is in {layer_crs}; the project is in {project_crs}. On-the-fly reprojection hides "
                "this, but your analysis won't. Reproject Layer is in the Processing Toolbox."],
            2: ["{layer_crs} and {project_crs} in one project? Bold. It'll draw fine. Your buffers won't. "
                "Reproject '{name}' before measuring anything."],
            3: ["{layer_crs}?! The project is {project_crs}! Reproject '{name}' before your distances start "
                "lying to you. They WILL lie."],
        },
    },
    "no_crs": {
        "min_level": 0, "cooldown": 300, "anim": "thinking", "title": "Unknown CRS",
        "texts": {
            0: ["'{name}' has no CRS. Set one in Layer Properties > Source, or it may end up in the wrong place."],
            2: ["'{name}' has no CRS. It could be anywhere. Literally. Set one in Layer Properties > Source."],
            3: ["'{name}' doesn't know where it is. Neither do I. Layer Properties > Source. Please."],
        },
    },
    "unsaved_project": {
        "min_level": 0, "cooldown": 1200, "anim": "tap_glass", "title": "Unsaved project",
        "texts": {
            0: ["The project has had unsaved changes for {minutes} minutes. Ctrl+S saves it."],
            1: ["{minutes} minutes of unsaved work. Ctrl+S. Just saying."],
            2: ["{minutes} minutes without saving. Living dangerously, I see. Ctrl+S."],
            3: ["{minutes} MINUTES. UNSAVED. One crash and it's gone. CTRL. PLUS. S."],
        },
    },
    "uncommitted_edits": {
        "min_level": 0, "cooldown": 900, "anim": "tap_glass", "title": "Unsaved edits",
        "texts": {
            0: ["'{name}' has edits that have not been saved for {minutes} minutes. Use Save Layer Edits in "
                "the Digitizing toolbar."],
            1: ["'{name}' has been in edit mode with unsaved changes for {minutes} minutes. Save Layer Edits "
                "is right there."],
            2: ["Your edits to '{name}' are {minutes} minutes old and still unsaved. Commitment issues?"],
            3: ["'{name}': {minutes} minutes of uncommitted edits. Save them. SAVE THEM."],
        },
    },
    "scratch_on_save": {
        "min_level": 0, "cooldown": 600, "anim": "nervous", "title": "Temporary layers",
        "texts": {
            0: ["Project saved, but {count} temporary scratch layer(s) live only in memory and will be lost "
                "when QGIS closes. Right-click them > Make Permanent."],
            2: ["Saved! Except the {count} scratch layer(s), which will evaporate when you close QGIS. "
                "Right-click > Make Permanent."],
            3: ["You saved the project but NOT the {count} scratch layer(s). They will vanish. Like tears in "
                "rain. Right-click > Make Permanent."],
        },
    },
    "processing_error": {
        "min_level": 0, "cooldown": 300, "group": "errors", "anim": "nervous", "title": "Processing error",
        "texts": {
            0: ["A Processing algorithm reported an error. Details are in the Log Messages panel "
                "(Processing tab)."],
            2: ["Processing failed. Before you blame QGIS: check the Log Messages panel. It's usually "
                "geometry. Or CRS. Or both."],
            3: ["PROCESSING EXPLODED. The Log Messages panel knows why. I suspect invalid geometries."],
        },
    },
    "python_error": {
        "min_level": 0, "cooldown": 300, "group": "errors", "anim": "surprised", "title": "Python error",
        "texts": {
            0: ["A Python error occurred, probably in a plugin. Details are in the Log Messages panel."],
            1: ["A Python error just happened. Not me. Probably. Check the Log Messages panel."],
            3: ["Python error! It wasn't me. I was here the whole time. Bending."],
        },
    },
    "error_bar": {
        "min_level": 0, "cooldown": 300, "group": "errors", "anim": "surprised", "title": "Something went wrong",
        "texts": {
            0: ["QGIS reported an error in the message bar. The Log Messages panel may have more detail."],
            2: ["Red bar of doom. The Log Messages panel has the gory details."],
        },
    },
    "no_spatial_index": {
        "min_level": 0, "cooldown": 600, "anim": "idea", "title": "Spatial index",
        "texts": {
            0: ["'{name}' has {count} features and no spatial index. Create one (Layer Properties > Source > "
                "Create Spatial Index) to speed up drawing and analysis."],
            2: ["{count} features and no spatial index on '{name}'. Enjoy the wait, or go to Layer "
                "Properties > Source > Create Spatial Index."],
        },
    },
    "invalid_geometries": {
        "min_level": 0, "cooldown": 600, "anim": "search", "title": "Invalid geometries",
        "texts": {
            0: ["{count} of the first {sample} features in '{name}' have invalid geometries. Fix Geometries "
                "(Processing Toolbox) can repair most of them."],
            2: ["I found {count} broken geometries in the first {sample} features of '{name}'. Fix Geometries "
                "exists. Use it before Processing complains."],
            3: ["'{name}' has invalid geometries. {count} in the first {sample}! Self-intersections "
                "everywhere! Fix Geometries! NOW!"],
        },
    },
    "slow_render": {
        "min_level": 0, "cooldown": 900, "anim": "yawn", "title": "Slow rendering",
        "texts": {
            0: ["That map render took {seconds} s. Scale-dependent visibility, spatial indexes or simplified "
                "geometries can speed it up."],
            2: ["{seconds} seconds to draw the map. I aged. Try scale-dependent visibility or a spatial index."],
        },
    },
    "first_layout": {
        "min_level": 0, "cooldown": 3600, "anim": "wave", "title": "New layout",
        "texts": {
            0: ["Starting a print layout. Tip: Atlas (Atlas panel in the layout designer) creates one page "
                "per feature of a coverage layer."],
            1: ["It looks like you're trying to make a map. Would you like help?<br><br>"
                "Tip: Atlas creates one page per feature."],
            3: ["IT LOOKS LIKE YOU'RE TRYING TO MAKE A MAP. I've waited my whole life for this moment."],
        },
    },
    # ------------------------------------------------------------- harass
    "shapefile": {
        "min_level": 1, "cooldown": 900, "anim": "spell_gpkg", "title": "A shapefile",
        "texts": {
            1: ["'{name}' is a shapefile. GeoPackage is a single file with no 10-character field name limit. "
                "Just a thought."],
            2: ["A shapefile? In {year}? GeoPackage would like a word."],
            3: ["SHAPEFILE DETECTED. .shp .shx .dbf .prj .cpg... how many files does one layer NEED?!"],
        },
    },
    "many_shapefiles": {
        "min_level": 1, "cooldown": 3600, "anim": "spell_shp", "title": "Shapefiles",
        "texts": {
            1: ["This project has {count} shapefile layers. A single GeoPackage could hold them all."],
            2: ["{count} shapefiles. That's about {files} files on disk. Have you met GeoPackage?"],
            3: ["{count} SHAPEFILES. ~{files} FILES. I need to lie down."],
        },
    },
    "osm_basemap": {
        "min_level": 2, "cooldown": 3600, "anim": "reading", "title": None,
        "texts": {
            2: ["OpenStreetMap basemap. Classic. Don't forget the attribution in your layout."],
            3: ["OSM basemap! Crowd-sourced by millions, attributed by... you, right? RIGHT?"],
        },
    },
    "lazy_names": {
        "min_level": 1, "cooldown": 1800, "anim": "suspicious", "title": "Layer names",
        "texts": {
            1: ["{count} layers have default names like '{name}'. Right-click > Rename Layer so future you "
                "knows what they are."],
            2: ["'{name}', '{name}', '{name}'... {count} layers with default names. Very descriptive."],
            3: ["{count} layers named things like '{name}'. In six months you will hate yourself. Rename them."],
        },
    },
    "many_layers": {
        "min_level": 1, "cooldown": 3600, "anim": "dizzy", "title": "That's a lot of layers",
        "texts": {
            1: ["{count} layers. Groups keep the Layers panel manageable."],
            2: ["{count} layers. My wire isn't long enough to scroll through that."],
            3: ["{count} LAYERS. I tried counting them and got dizzy."],
        },
    },
    "zoom_thrash": {
        "min_level": 1, "cooldown": 900, "anim": "dizzy", "title": None,
        "texts": {
            1: ["Lost? Right-click a layer > Zoom to Layer, or save the view as a Spatial Bookmark."],
            2: ["In, out, in, out. You're zooming like you lost your keys."],
            3: ["STOP ZOOMING. I'm getting seasick. Zoom to Layer exists."],
        },
    },
    "web_mercator": {
        "min_level": 1, "cooldown": 1800, "anim": "annoyed", "title": "Web Mercator",
        "texts": {
            1: ["Project CRS is now Web Mercator (EPSG:3857). Fine for web maps; areas and distances are badly "
                "distorted away from the equator."],
            2: ["Web Mercator. Where Greenland is the size of Africa and your area calculations are fiction."],
            3: ["EPSG:3857?! Greenland is NOT that big! Measure NOTHING in this CRS!"],
        },
    },
    "comic_sans": {
        "min_level": 1, "cooldown": 3600, "anim": "annoyed", "title": "Font choice",
        "texts": {
            1: ["That layout uses {font}. Bold choice for a map."],
            2: ["{font}. In a map layout. I've seen things."],
            3: ["{font}?!?! I'm a paperclip and even I have standards."],
        },
    },
    "late_night": {
        "min_level": 1, "cooldown": 86400, "anim": "yawn", "title": None,
        "texts": {
            1: ["It's {time}. Maps made after midnight have 40% more typos. I made that statistic up."],
            2: ["{time}. Shouldn't you be asleep? I'm a paperclip and even I'm tired."],
            3: ["IT IS {time}. GO TO BED. The map will still be wrong in the morning."],
        },
    },
    "long_session": {
        "min_level": 1, "cooldown": 86400, "anim": "yawn", "title": None,
        "texts": {
            1: ["You've been at this for {hours} hours. Stretch, drink some water, save the project."],
            2: ["{hours} hours straight. Your chair has merged with you. Take a break."],
            3: ["{hours} HOURS. Blink. Breathe. Touch grass (not the GIS kind)."],
        },
    },
    "layer_removed": {
        "min_level": 2, "cooldown": 600, "chance": 0.35, "anim": "sad", "title": None,
        "texts": {
            2: ["Goodbye, '{name}'. You will be missed. Probably."],
            3: ["NOOO, not '{name}'! We had such good times. Well. Some times."],
        },
    },
    "saved_praise": {
        "min_level": 2, "cooldown": 1800, "chance": 0.25, "anim": "spell_qgis", "title": None,
        "texts": {
            2: ["Saved! I'm proud of you."],
            3: ["YOU SAVED! Party time! This is the best day of my life!"],
        },
    },
    "warning_bar": {
        "min_level": 2, "cooldown": 900, "chance": 0.3, "anim": "nervous", "title": None,
        "texts": {
            2: ["A warning in the message bar. I saw that."],
            3: ["Warning! WARNING! ...it's probably fine."],
        },
    },
    "success_bar": {
        "min_level": 2, "cooldown": 900, "chance": 0.25, "anim": "sparkle", "title": None,
        "texts": {
            2: ["Success! Nice."],
            3: ["SUCCESS! Look at you go!"],
        },
    },
}

# Layer names and temporary layers.
RULES.update({
    "generic_layer_name": {
        "min_level": 1, "cooldown": 600, "chance": 0.5, "anim": "suspicious", "title": None,
        "texts": {
            1: ["'{name}'. Future you will have no idea what that is. Right-click > Rename Layer."],
            2: ["Ah, '{name}'. A name as unique as a snowflake. In a blizzard."],
            3: ["'{name}'?! Give it a REAL name! It has feelings! Probably!"],
        },
    },
    "temporary_layer_added": {
        "min_level": 1, "cooldown": 900, "chance": 0.35, "anim": "nervous", "title": None,
        "texts": {
            1: ["'{name}' is a temporary layer. It disappears when QGIS closes unless you make it permanent."],
            2: ["'{name}' lives in memory. Memory is fleeting. Like your unsaved work."],
            3: ["TEMPORARY LAYER! '{name}' will VANISH! Right-click > Make Permanent before it's too late!"],
        },
    },
    "generic_temporary_layer": {
        "min_level": 1, "cooldown": 600, "chance": 0.6, "anim": "eye_roll", "title": None,
        "texts": {
            1: ["Another temporary layer called '{name}'. Temporary and anonymous: a risky combination."],
            2: ["'{name}': temporary AND generically named. It's like it wants to be forgotten."],
            3: ["'{name}'! No real name, no file, no future! Make it permanent and NAME IT!"],
        },
    },
    "many_temporary_layers": {
        "min_level": 0, "cooldown": 1800, "anim": "nervous", "title": "Temporary layers",
        "texts": {
            0: ["{count} layers are temporary (in memory) and will be lost when QGIS closes. Right-click "
                "> Make Permanent to keep them."],
            1: ["{count} temporary layers, including '{name}'. They won't survive closing QGIS."],
            2: ["{count} temporary layers. You're one crash away from a very bad afternoon."],
            3: ["{count} TEMPORARY LAYERS. That's {count} things that will EVAPORATE. Make them permanent!"],
        },
    },
})

# Processing runs (from the Processing history).
RULES.update({
    "processing_crs_mismatch": {
        "min_level": 0, "cooldown": 300, "anim": "tap_map", "title": "Mixed CRSs",
        "texts": {
            0: ["You're running {algorithm} on layers in different CRSs ({crs_list}). Some algorithms "
                "reproject on the fly; it's safer to reproject the inputs to one CRS first."],
            1: ["{algorithm} with inputs in {crs_list}? Reproject them to one CRS first, just to be safe."],
            2: ["{algorithm} on {crs_list}. Mixed CRSs. I'm sure it'll be fine. (It might not be fine.)"],
            3: ["{crs_list}?! In ONE {algorithm}?! I'm calling the projection police."],
        },
    },
    "buffer_in_degrees": {
        "min_level": 0, "cooldown": 300, "anim": "thinking", "title": "Distance in degrees",
        "texts": {
            0: ["'{name}' is in {crs}, a geographic CRS, so the distance {distance} in {algorithm} is in "
                "degrees. Reproject to a projected CRS to use metres."],
            1: ["{algorithm} by {distance}... degrees? '{name}' is in {crs}. That's a big buffer."],
            2: ["A {distance}-degree {algorithm}. Bold. Hope you meant to cover a few countries."],
            3: ["{distance} DEGREES?! '{name}' is in {crs}! You're about to buffer half a continent!"],
        },
    },
    "processing_temporary_outputs": {
        "min_level": 1, "cooldown": 1800, "anim": "eye_roll", "title": None,
        "texts": {
            1: ["That's {count} temporary outputs this session. Saving them to a GeoPackage keeps them safe."],
            2: ["{count} temporary outputs. Your RAM is your filing system now?"],
            3: ["{count} TEMPORARY OUTPUTS. Save one. Just one. For me."],
        },
    },
    "processing_repeat": {
        "min_level": 1, "cooldown": 900, "anim": "suspicious", "title": None,
        "texts": {
            1: ["{algorithm} again? That's {count} runs. Processing > History has your previous settings."],
            2: ["{algorithm}, attempt number {count}. Third time's the charm. Or fourth."],
            3: ["{algorithm} {count} TIMES. It's not going to change its mind."],
        },
    },
    "processing_fix_geometries": {
        "min_level": 1, "cooldown": 1800, "chance": 0.5, "anim": "nod", "title": None,
        "texts": {
            1: ["Fixing geometries first. Good habit."],
            2: ["Fix Geometries! Look at you, being responsible."],
            3: ["FIX GEOMETRIES! My favourite algorithm! I'm so proud!"],
        },
    },
    "processing_invalid_geometries_log": {
        "min_level": 0, "cooldown": 600, "anim": "search", "title": "Invalid geometries",
        "texts": {
            0: ["{algorithm} reported invalid geometries; some features may have been skipped. Run Fix "
                "Geometries on the input and try again."],
            2: ["{algorithm} hit invalid geometries and probably skipped some features. Fix Geometries, then retry."],
            3: ["INVALID GEOMETRIES in {algorithm}! Features got SKIPPED! Fix Geometries! Now!"],
        },
    },
    "processing_done": {
        "min_level": 2, "cooldown": 600, "chance": 0.25, "anim": "sparkle", "title": None,
        "texts": {
            2: ["{algorithm} done. Did it do what you wanted? Check before you trust it."],
            3: ["{algorithm} FINISHED! Is it right? Is it?! Look at it!"],
        },
    },
})

# Errors, mocked by kind (all share the "errors" cooldown with the generic ones above).
_ERROR = {"cooldown": 300, "group": "errors"}
RULES.update({
    "error_file": dict(_ERROR, min_level=0, anim="search", title="File not found", texts={
        0: ["QGIS couldn't find or open a file ({detail}). If data moved, Layer > Data Source Manager or the "
            "'Handle Unavailable Layers' dialog can repoint it."],
        1: ["A file has gone missing: {detail}. Did it move, or did it run away?"],
        2: ["{detail}. The file isn't there. I checked. Behind the map and everything."],
        3: ["FILE NOT FOUND! {detail}! Who moved it?! Was it you? It was you."],
    }),
    "error_permission": dict(_ERROR, min_level=0, anim="annoyed", title="Permission denied", texts={
        0: ["QGIS wasn't allowed to read or write a file ({detail}). It may be open in another program "
            "or in a read-only folder."],
        2: ["Permission denied. The file said no. Respect its boundaries. Or close Excel."],
        3: ["ACCESS DENIED! Is that file open in another program?! It's ALWAYS open in another program!"],
    }),
    "error_geometry": dict(_ERROR, min_level=0, anim="search", title="Geometry error", texts={
        0: ["An error mentions geometry ({detail}). Run Check Validity or Fix Geometries on the input."],
        2: ["A geometry error. Your polygons are tying themselves in knots. Fix Geometries."],
        3: ["GEOMETRY ERROR! Self-intersections! Bowties! CHAOS! Fix Geometries!"],
    }),
    "error_crs": dict(_ERROR, min_level=0, anim="tap_map", title="CRS / transform error", texts={
        0: ["An error mentions a CRS or coordinate transform ({detail}). Check that each layer's CRS is set correctly."],
        2: ["A transform error. Somewhere a coordinate is crying. Check your CRSs."],
        3: ["PROJECTION ERROR! The Earth is round and your CRSs are a MESS!"],
    }),
    "error_memory": dict(_ERROR, min_level=0, anim="dizzy", title="Out of memory", texts={
        0: ["QGIS ran out of memory. Try a smaller extent, fewer temporary layers, or saving outputs to files."],
        2: ["Out of memory. Even QGIS has limits. Mostly because of your temporary layers."],
        3: ["OUT OF MEMORY! Too much! It's TOO MUCH DATA! Save something to disk!"],
    }),
    "error_none": dict(_ERROR, min_level=0, anim="shake_head", title="Python error", texts={
        0: ["A {error_type} about None: something expected a layer or value that wasn't there. Details are in "
            "the Log Messages panel."],
        1: ["'NoneType' strikes again. Something wasn't there when it was needed."],
        2: ["NoneType has no attribute. The most Python error of all time."],
        3: ["NONETYPE! The void stared back! Something is MISSING and it's probably a layer!"],
    }),
    "error_field": dict(_ERROR, min_level=0, anim="thinking", title="Field error", texts={
        0: ["An error mentions a field or attribute ({detail}). Check the field names in the attribute table."],
        2: ["Field not found. Maybe it got truncated to 10 characters? Shapefiles do that."],
        3: ["THE FIELD DOES NOT EXIST! Maybe it's in a shapefile and lost half its name!"],
    }),
    "error_network": dict(_ERROR, min_level=0, anim="nervous", title="Connection problem", texts={
        0: ["A network error ({detail}). Check your connection or the service URL."],
        2: ["The internet said no. Or the server's napping. Try again later."],
        3: ["NO CONNECTION! We're alone out here! Just you, me and a cached basemap!"],
    }),
    "error_database": dict(_ERROR, min_level=0, anim="thinking", title="Database error", texts={
        0: ["A database or SQL error ({detail}). Check the query, the connection and the table name."],
        2: ["SQL error. Missing comma? Missing quote? Missing will to live?"],
        3: ["SQL ERROR! It's always a missing comma! ALWAYS!"],
    }),
    "error_mine": dict(_ERROR, min_level=0, anim="sad", title="Qlippy error", texts={
        0: ["That error came from Qlippy. Sorry. Please report it on the plugin's issue tracker."],
        2: ["Okay, that one was me. I'm only a paperclip. Please report it."],
        3: ["That was ME. I broke something. I'm so ashamed. Report me."],
    }),
    "error_streak": {
        "min_level": 1, "cooldown": 1200, "anim": "dizzy", "title": None,
        "texts": {
            1: ["That's {count} errors in ten minutes. Maybe take a step back?"],
            2: ["{count} errors in ten minutes. Is this a personal best?"],
            3: ["{count} ERRORS! We're on a ROLL! A roll downhill! Into a ditch!"],
        },
    },
})

# Empty, duplicated and misplaced layers.
RULES.update({
    "empty_layer": {
        "min_level": 0, "cooldown": 600, "anim": "search", "title": "Empty layer",
        "texts": {
            0: ["'{name}' has no features. Check the source, or any filter set in Layer Properties > Source."],
            1: ["'{name}' is empty. Not a single feature. Very minimalist."],
            2: ["'{name}': zero features. I looked everywhere. Even under the map."],
            3: ["'{name}' IS EMPTY! It's a layer of NOTHING! The void has a name now!"],
        },
    },
    "empty_output": {
        "min_level": 0, "cooldown": 600, "anim": "search", "title": "Empty result",
        "texts": {
            0: ["'{name}' has no features. If it came from Processing, check the inputs overlap, share a CRS "
                "and that 'selected features only' wasn't ticked by mistake."],
            1: ["'{name}' came out empty. The inputs probably don't overlap. Or the CRSs don't agree."],
            2: ["Congratulations, '{name}' contains exactly nothing. Masterful."],
            3: ["'{name}': ZERO FEATURES! All that processing for NOTHING! Check the CRSs!"],
        },
    },
    "new_scratch_layer": {
        "min_level": 1, "cooldown": 900, "chance": 0.5, "anim": "wave", "title": None,
        "texts": {
            1: ["A fresh scratch layer. Remember it only lives in memory until you make it permanent."],
            2: ["An empty scratch layer! A blank canvas! Please name it something better than '{name}'."],
            3: ["NEW SCRATCH LAYER! So much potential! So likely to be forgotten!"],
        },
    },
    "duplicate_layer": {
        "min_level": 1, "cooldown": 600, "anim": "suspicious", "title": None,
        "texts": {
            1: ["'{name}' is already in the project. Did you mean to add it twice?"],
            2: ["'{name}' again? Twice the layer, twice the confusion."],
            3: ["'{name}' AGAIN?! Are we collecting them now?!"],
        },
    },
    "null_island_layer": {
        "min_level": 0, "cooldown": 600, "anim": "pin_drop", "title": "Null Island",
        "texts": {
            0: ["'{name}' sits around 0\u00b0, 0\u00b0 (Null Island). Its coordinates or its CRS are probably wrong."],
            2: ["'{name}' is on Null Island. Lovely beaches. Wrong CRS, probably."],
            3: ["'{name}' WENT TO NULL ISLAND! Send help! Or the right CRS!"],
        },
    },
    "layer_regret": {
        "min_level": 2, "cooldown": 600, "chance": 0.6, "anim": "laugh", "title": None,
        "texts": {
            2: ["Added and removed '{name}' in {seconds} seconds. Commitment issues?"],
            3: ["'{name}' lasted {seconds} SECONDS. That's a new record!"],
        },
    },
})

# ---------------------------------------------------------------- remarks
TIPS = [
    "Press Ctrl+K to use the locator: search layers, features, actions and Processing algorithms.",
    "Ctrl+Alt+T toggles the Processing Toolbox.",
    "F6 opens the attribute table of the selected layer.",
    "F7 toggles the Layer Styling panel; style changes apply live.",
    "Hold the Space bar and move the mouse to pan the map, whatever tool is active.",
    "Processing > History lets you re-run an algorithm with the same parameters.",
    "Right-click an algorithm in the Processing Toolbox > Execute as Batch Process to run it on many inputs.",
    "Right-click a layer > Export > Save Features As... to convert it to GeoPackage.",
    "Rule-based symbology styles features by expression.",
    "The Field Calculator can update existing fields, not only create new ones.",
    "Virtual fields (Field Calculator > Create virtual field) update automatically when data changes.",
    "Spatial Bookmarks save map views you return to often.",
    "Temporary scratch layers disappear when QGIS closes. Right-click > Make Permanent to keep them.",
    "You can drag files from your file manager straight onto the map.",
    "The Browser panel can create, rename and delete GeoPackage tables.",
    "Map themes (the eye icon in the Layers panel) save layer visibility and styles.",
    "The Statistics panel summarises a field in one click.",
    "Scale-dependent visibility hides detailed layers when zoomed out and speeds up rendering.",
    "The measure tool uses the project ellipsoid: Project > Properties > General.",
    "Atlas in print layouts generates one map page per feature.",
    "Styles can be saved as .qml files and reused, or saved as a layer's default style.",
    "Right-click a layer > Styles > Copy Style, then Paste Style onto another layer.",
    "The Model Designer chains Processing algorithms into a reusable model.",
    "Check Validity finds invalid geometries; Fix Geometries repairs most of them.",
    "A GeoPackage can hold many layers, their styles and even QGIS projects in one file.",
    "Expressions can use variables like @project_title in labels and layouts.",
    "Project > Properties > Relations links tables so forms show related records.",
    "Hold Shift while selecting features to add to the current selection.",
    "Layer notes (right-click > Layer Notes) store comments with a layer in the project.",
    "The Identify tool shows attributes; set its mode to 'Top down' to query all layers at once.",
    "Settings > Options > Rendering controls parallel rendering and feature simplification.",
    "Snapping options are under Project > Snapping Options.",
    "Use 'Zoom to Native Resolution' on raster layers to see pixels 1:1.",
    "Labels can be placed manually with the label toolbar's Move Label tool.",
]

TIP_PREFIX = {
    0: [""],
    1: ["Psst. ", "Free advice: ", "Did you know? ", "Tip: ", "Hey. "],
    2: ["Listen. ", "Pro tip, since you clearly need one: ", "Here's something useful for once: ",
        "Write this down: "],
    3: ["TIP!!! ", "LISTEN TO ME: ", "I KNOW THINGS: ", "Mandatory fun fact: "],
}

QUIPS = {
    1: [
        "It looks like you're making a map. Would you like help with that?",
        "I'm a paperclip. Holding things together is literally my job. Like your project.",
        "Remember: a map without a legend is just modern art.",
        "North arrow? Scale bar? Just checking.",
        "Have you tried turning the layer off and on again?",
        "Every map is wrong. Some are just more wrong than others.",
        "Fun fact: Greenland is not that big. Mercator lied to you.",
        "I'd offer to hold your coffee but I'm a paperclip.",
        "Save early, save often.",
        "Nice map. Did you mean to do that?",
        "I'm not saying you need help. I'm just standing here. On a map. Ready.",
    ],
    2: [
        "That colour ramp is... a choice.",
        "I'd help, but you look like you've got this. Mostly.",
        "Is this map for a client or for revenge?",
        "If you need me, I'll be here. Watching. Bending.",
        "The attribute table called. It wants its NULLs back.",
        "Somewhere, a cartographer just felt a disturbance.",
        "Fun fact: I was a straight wire once. Then I saw your symbology.",
        "Projections are like opinions. Everyone has one, and EPSG has thousands more.",
        "You know you can delete layers, right? Asking for a friend.",
        "Ah yes, the classic 'zoom to world, then zoom back in' technique.",
        "I'm not judging. I'm just a paperclip with eyebrows.",
    ],
    3: [
        "I SEE YOUR UNSAVED CHANGES. Probably. I can't actually see. Or can I?",
        "Every time someone uses a rainbow colour ramp, a cartographer loses a pixel.",
        "What if the map is projecting YOU?",
        "I counted your layers. I will not say the number. It haunts me.",
        "Shapefiles have a 10-character field name limit. I have a 0-character patience limit.",
        "Click me. Click me. Click me. No, don't.",
        "I'm not saying the map is bad. I'm just bending away from it.",
        "The Earth is an oblate spheroid and so is my patience.",
        "Ctrl+Z won't undo this conversation.",
        "Do you ever think about how a world map is just a sphere that's been through a lot?",
        "I used to hold TPS reports. Now I hold opinions about your symbology.",
        "Null Island is beautiful this time of year. Your data seems to think so too.",
    ],
}

QUIP_ANIMS = ["brow_wiggle", "suspicious", "laugh", "look_around", "eye_roll", "stare", "wave",
              "shuffle", "tap_glass", "thinking"]

TITLES = {0: "Tip", 1: "Psst", 2: "Listen", 3: "HEY"}

GREETINGS = {
    "morning": {0: ["Good morning. Ready when you are."],
                1: ["Morning! Coffee first, then maps."],
                2: ["Morning. Let's see what we're breaking today."],
                3: ["GOOD MORNING! I've been waiting ALL NIGHT."]},
    "afternoon": {0: ["Good afternoon. Ready when you are."],
                  1: ["Afternoon! It looks like you're about to make a map."],
                  2: ["Oh, it's you. Let's do some GIS, I guess."],
                  3: ["YOU'RE BACK! Let's make a map! Let's make TEN!"]},
    "evening": {0: ["Good evening. Ready when you are."],
                1: ["Evening shift? Let's make it quick."],
                2: ["Working in the evening? Bold. Let's go."],
                3: ["EVENING MAPPING! The best mapping! Probably!"]},
    "night": {0: ["Working late. I'm here if you need me."],
              1: ["It's late. Let's not make this an all-nighter."],
              2: ["Night owl, huh? Fine. I'm awake too."],
              3: ["WHY ARE WE AWAKE. Let's map anyway."]},
}

WAKE = {1: ["Oh! I wasn't sleeping. I was... resting my eyes."],
        2: ["Huh? What? I'm up. I'm up.", "Oh, you're back. I dreamt of a perfectly topological dataset."],
        3: ["WHO'S THERE?! Oh. It's you. I dreamt about shapefiles. It was a nightmare."]}

POKE = {0: ["Click me again for another tip."],
        1: ["Okay, okay, I'm here.", "That tickles."],
        2: ["Stop poking me.", "Do I poke YOU while you work?"],
        3: ["POKE ME ONE MORE TIME.", "I am a paperclip, not a stress ball!"]}

DRAG = {2: ["Wheee!", "Put me down!", "Where are we going?"],
        3: ["WHEEEEE!", "I'M FLYING!", "Careful, I bend!"]}

SNOOZE = {0: ["Okay. I'll be quiet for {duration}."],
          1: ["Fine. Quiet for {duration}."],
          2: ["Fine. I'll sulk quietly for {duration}."],
          3: ["FINE. Silence for {duration}. You'll miss me."]}

UNSNOOZE = {0: ["I'm back."], 1: ["Did you miss me?"], 2: ["I'm back. Did you break anything?"],
            3: ["I'M BACK, BABY!"]}

LEVEL_CHANGE = {0: ("Helpful mode. Tips only, no attitude.", "nod"),
                1: ("Cheeky mode. Just a little attitude.", "brow_wiggle"),
                2: ("Sassy mode. You asked for it.", "suspicious"),
                3: ("UNHINGED MODE. Oh, this is going to be fun.", "celebrate")}

DISMISS_LABEL = {0: "OK", 1: "Got it", 2: "Yeah, yeah", 3: "Leave me alone"}
DISABLE_LABEL = {0: "Don't show again", 1: "Don't show again", 2: "Stop nagging", 3: "NEVER AGAIN"}
ANOTHER_LABEL = {0: "Another tip", 1: "Another one", 2: "More", 3: "MORE"}


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def by_level(table, level):
    """Return the entry for level, falling back to the nearest lower level."""
    for candidate_level in range(level, -1, -1):
        if candidate_level in table and table[candidate_level]:
            return table[candidate_level]
    for candidate_level in sorted(table):
        if table[candidate_level]:
            return table[candidate_level]
    return None


MAX_VALUE_LENGTH = 48
SOFT_BREAK_AFTER = "_./\\-:|"
ZERO_WIDTH_SPACE = "\u200b"


def shorten(value, limit=MAX_VALUE_LENGTH):
    """Make a name safe to show in a speech bubble.

    - paths and data sources become their file name,
    - anything longer than `limit` keeps its start and end with "..." between.
    """
    text = " ".join(str(value).split())
    if " " not in text and ("/" in text or "\\" in text):
        text = text.split("|")[0].replace("\\", "/").rstrip("/").split("/")[-1] or text
    if len(text) > limit:
        tail = max(8, limit // 3)
        text = text[: limit - tail - 1] + "\u2026" + text[-tail:]
    return text


def _soft_breaks(escaped_text, word_limit=18):
    """Let very long words wrap by adding invisible break points after _ . / - : |"""
    words = []
    for word in escaped_text.split(" "):
        if len(word) > word_limit:
            for char in SOFT_BREAK_AFTER:
                word = word.replace(char, char + ZERO_WIDTH_SPACE)
        words.append(word)
    return " ".join(words)


def fmt(text, **values):
    escaped = _SafeDict({key: _soft_breaks(html.escape(shorten(value))) for key, value in values.items()})
    return text.format_map(escaped)


RECENT_MEMORY = 6  # don't reuse any of a rule's last few messages
_recent_texts = {}


def _join(*pieces):
    """Join message pieces, capitalising a piece that starts a new sentence."""
    out = ""
    for piece in pieces:
        if not piece:
            continue
        if out and out.rstrip()[-1:] in ".!?" and piece[:1].islower():
            piece = piece[:1].upper() + piece[1:]
        out = (out + " " + piece) if out else piece
    return out


def _candidate_texts(rule_id, level):
    """All wordings for a rule at a level: composed ones if available, else the plain list."""
    parts = by_level(COMPOSED.get(rule_id, {}), level)
    if parts:
        openings, middles, endings = parts
        return [_join(opening, middle, ending)
                for opening in openings for middle in middles for ending in endings]
    return by_level(RULES[rule_id]["texts"], level)


def rule_text(rule_id, level, rng=random, **values):
    """A message for a rule, avoiding the wordings it used most recently."""
    options = _candidate_texts(rule_id, level)
    recent = _recent_texts.setdefault(rule_id, [])
    fresh = [text for text in options if text not in recent] or options
    template = rng.choice(fresh)
    recent.append(template)
    del recent[:-min(RECENT_MEMORY, max(1, len(options) - 1))]
    return personalize(fmt(template, year=datetime.date.today().year, **values), level, rng)


def pick(table, level, rng=random, **values):
    options = by_level(table, level)
    return personalize(fmt(rng.choice(options), **values), level, rng) if options else ""


def tip(level, rng=random):
    pool = TIPS
    prefix = rng.choice(TIP_PREFIX.get(level, [""]))
    return html.escape(prefix + rng.choice(pool))


def random_remark(level, rng=random):
    """(html_text, title, animation) for an unprompted remark."""
    tip_share = {0: 1.0, 1: 0.65, 2: 0.4, 3: 0.25}[level]
    if rng.random() < tip_share:
        return personalize(tip(level, rng), level, rng), TITLES[level], personality_anim("idea", rng)
    quips = current_personality().get("quips")
    if quips and rng.random() < 0.55:
        return html.escape(rng.choice(quips)), None, personality_anim(rng.choice(QUIP_ANIMS), rng)
    levels = list(range(1, level + 1))
    weights = [quip_level for quip_level in levels]  # favour the current level
    quip_level = rng.choices(levels, weights=weights)[0]
    return html.escape(rng.choice(QUIPS[quip_level])), None, rng.choice(QUIP_ANIMS)


def greeting(level, now=None, rng=random):
    hour = (now or datetime.datetime.now()).hour
    if 5 <= hour < 12:
        part = "morning"
    elif 12 <= hour < 18:
        part = "afternoon"
    elif 18 <= hour < 23:
        part = "evening"
    else:
        part = "night"
    own = current_personality().get("greetings")
    if own:
        return html.escape(rng.choice(own))
    return pick(GREETINGS[part], level, rng)


# ------------------------------------------------------------- wandering
WANDER = {
    "layers": {
        0: ["{count} layers in {groups} group(s). Tip: right-click a group > Set Group CRS, or drag layers to reorder them."],
        1: ["Just browsing your layers. {count} of them. Nice collection."],
        2: ["{count} layers. I've seen tidier Layers panels. I've also seen worse. Not many."],
        3: ["{count} LAYERS. I'm standing on them. Metaphorically. Literally, a bit."],
    },
    "layers_empty": {
        0: ["No layers yet. Drag a file onto the map or use Layer > Add Layer."],
        1: ["An empty Layers panel. So much potential."],
        2: ["Zero layers. Bold minimalist approach."],
        3: ["NOTHING. There's NOTHING here. Add a layer! Any layer!"],
    },
    "layers_lazy": {
        0: ["{lazy} layers still have default names like '{name}'. Right-click > Rename Layer."],
        2: ["'{name}'. Riveting name. There are {lazy} of these."],
        3: ["I found '{name}' and {lazy} others like it. Name your layers, you monster."],
    },
    "layers_hidden": {
        0: ["{hidden} layers are switched off. Map themes can save different visibility combinations."],
        2: ["{hidden} hidden layers. What are you hiding?"],
        3: ["{hidden} INVISIBLE LAYERS. Are they ghosts? Are they shy? Delete them or love them."],
    },
    "save_dirty": {
        0: ["This is the Save Project button. The project has unsaved changes."],
        1: ["Psst. This button. You know what to do."],
        2: ["I'm just going to stand next to the save button. No reason. Unsaved changes. No reason."],
        3: ["PRESS IT. PRESS THE BUTTON. I'll wait right here."],
    },
    "save_clean": {
        0: ["The project is saved. Ctrl+S whenever you change something."],
        2: ["Everything saved. I'm almost impressed."],
        3: ["Saved! For now. I'm watching."],
    },
    "statusbar": {
        0: ["The project CRS is {crs}. Click it in the status bar to change it."],
        1: ["Project CRS: {crs}. I checked."],
        2: ["{crs}. Interesting choice. I'll allow it."],
        3: ["{crs}! I have OPINIONS about {crs}. I'll keep them to myself. For now."],
    },
    "statusbar_mercator": {
        1: ["Web Mercator down here in the status bar. Fine for display, not for measuring."],
        2: ["EPSG:3857 in the status bar. Greenland says hi. It's enormous."],
        3: ["EPSG:3857!!! Every area you measure is a LIE."],
    },
    "statusbar_geographic": {
        0: ["The project CRS ({crs}) is geographic. Use a projected CRS for distance and area calculations."],
        2: ["{crs}: degrees. Buffer by 100 and you'll get 100 degrees. Ask me how I know."],
    },
    "canvas": {
        0: ["You're looking at roughly {lat}, {lon} at 1:{scale}."],
        1: ["Ooh, {lat}, {lon}. Nice spot."],
        2: ["1:{scale} around {lat}, {lon}. Very cartographic of you."],
        3: ["{lat}, {lon}! I've always wanted to go there! Have you? Take me!"],
    },
    "canvas_scale": {
        0: ["The map is at 1:{scale}."],
        2: ["1:{scale}. Zoom level: undecided."],
    },
    "canvas_empty": {
        0: ["The map is empty. Add a layer to get started."],
        2: ["An empty map. Very peaceful. Very useless."],
    },
    "canvas_null": {
        0: ["The map is centred near 0\u00b0, 0\u00b0. If your data is here unexpectedly, its CRS may be wrong."],
        2: ["Null Island! Your data's favourite holiday spot. Check the CRS."],
        3: ["NULL ISLAND! I KNEW IT EXISTED! ...your coordinates are probably broken though."],
    },
    "canvas_rotated": {
        0: ["The map is rotated. The rotation box in the status bar resets it."],
        2: ["Rotated map. North is wherever you say it is, I guess."],
    },
    "canvas_close": {
        0: ["Very close zoom (1:{scale}). Mind your data's precision."],
        2: ["1:{scale}. Are you counting the grass blades?"],
    },
    "canvas_world": {
        0: ["Zoomed out to 1:{scale}. Right-click a layer > Zoom to Layer to jump to your data."],
        2: ["The whole world at 1:{scale}. Looking for something?"],
    },
    "selection": {
        0: ["{count} features selected in '{name}'. Many tools have a 'Selected features only' option."],
        2: ["{count} selected features in '{name}'. Choosy."],
        3: ["You selected {count} features in '{name}'. WHY THOSE? What did the others do?"],
    },
    "processing": {
        0: ["The Processing Toolbox. Search it by name, or right-click an algorithm to run it as a batch."],
        2: ["Processing time! What are we breaking today?"],
        3: ["PROCESSING! My favourite! Run Fix Geometries first. Always. Trust me."],
    },
    "browser": {
        0: ["The Browser panel. Add folders to Favorites for quick access."],
        2: ["Browsing files. Looking for that one shapefile from 2009?"],
    },
    "attribute": {
        0: ["'{name}' has {fields} fields and {features} features."],
        2: ["{fields} fields, {features} features. And at least one NULL. There's always a NULL."],
        3: ["{features} ROWS. I'm going to read every single one. Starting... now. ...Never mind."],
    },
    "messagebar": {
        0: ["The message bar has something for you."],
        2: ["Something in the message bar. Did you read it? You didn't read it."],
    },
    "plugins": {
        1: ["Nice plugins. That paperclip one is especially good."],
        3: ["Look at all these plugins! None as good as me, obviously."],
    },
}


def wander_text(key, level, rng=random, **values):
    table = WANDER.get(key)
    if not table:
        return ""
    options = by_level(table, level)
    return personalize(fmt(rng.choice(options), **values), level, rng) if options else ""


CLICK_TEXT_CHANCE = {0: 0.2, 1: 0.3, 2: 0.4, 3: 0.5}
DEAD = {3: ["I'm dead. Look what you did.", "*plays dead*", "Tell my paper I loved it."]}


# ------------------------------------------------- peeking around dialogs
PEEK = {
    "processing": {
        0: ["Running {title}? Check the Log tab for warnings once it's done."],
        1: ["Ooh, {title}. What are we making?", "Psst. What's {title} doing?"],
        2: ["{title}, huh? Let me see. Move over.", "I can't see past {title}. Is it good?"],
        3: ["{title}! Let me SEE! I want to watch!", "Is {title} done yet? Is it? How about now?"],
    },
    "dialog": {
        1: ["Hello? I'm back here.", "Something's in the way."],
        2: ["Excuse me, you're blocking my view.", "Nice dialog. Very rectangular."],
        3: ["WHO PUT THIS WINDOW HERE.", "I can't see anything! Move it!"],
    },
}


def peek_text(kind, level, rng=random, **values):
    return personalize(pick(PEEK[kind], level, rng, **values), level, rng)


# ------------------------------------------------ reminders that may repeat
# These are genuinely useful, so they come back more often than other comments,
# but not every time (that gets annoying). To keep them from sounding canned,
# each is assembled from (openings, middles, endings).
# rule id: (cooldown in seconds, chance of speaking when it could)
REPEATABLE_RULES = {
    "scratch_on_save": (180, 0.8),
    "many_temporary_layers": (600, 0.7),
    "temporary_layer_added": (300, 0.5),
    "generic_temporary_layer": (300, 0.6),
    "processing_temporary_outputs": (600, 0.6),
    "processing_repeat": (300, 0.7),
}
for _rule_id, (_cooldown, _chance) in REPEATABLE_RULES.items():
    RULES[_rule_id]["cooldown"] = _cooldown
    RULES[_rule_id]["chance"] = _chance

COMPOSED = {
    "scratch_on_save": {
        0: (["Project saved, but", "Saved. Note that", "The project is saved; however,", "Saved, but heads up:"],
            ["{count} temporary layer(s) only exist in memory and will be lost when QGIS closes.",
             "{count} temporary layer(s) aren't stored in any file and will disappear when QGIS closes.",
             "{count} layer(s) are still temporary, so they weren't saved with the project."],
            ["Right-click > Make Permanent to keep them.", "Use right-click > Make Permanent to write them to a file.",
             "Make them permanent if you'll need them again."]),
        1: (["Saved! Well, mostly.", "Nice save. Small catch:", "Saved. One thing:", "Good save, but"],
            ["{count} temporary layer(s) are along for the ride in memory only.",
             "{count} temporary layer(s) won't survive closing QGIS.",
             "the {count} temporary layer(s) aren't in any file yet."],
            ["Make Permanent is in the right-click menu.", "Right-click > Make Permanent.", "Worth making them permanent."]),
        2: (["Saved! Ish.", "Congratulations on saving. Partially.", "Saved, except for the bits that matter?",
             "Oh, you saved. How thorough. Except"],
            ["{count} temporary layer(s) are still living in RAM like it's 1999.",
             "{count} temporary layer(s) will evaporate when you close QGIS.",
             "{count} temporary layer(s) are one crash away from never existing."],
            ["Right-click > Make Permanent. You know this.", "Make Permanent. Please.", "Your call. Your data."]),
        3: (["SAVED?! NOT REALLY!", "You saved! BUT!", "HALF A SAVE!", "SAVE ACHIEVED, MOSTLY!"],
            ["{count} TEMPORARY LAYER(S) WILL VANISH when you close QGIS!",
             "{count} layer(s) are still in MEMORY! Memory is a LIE!",
             "{count} temporary layer(s) are not in ANY file!"],
            ["MAKE THEM PERMANENT!", "Right-click! Make Permanent! GO!", "I'll be here. Worrying."]),
    },
    "many_temporary_layers": {
        0: (["The project now has", "Note: there are", "Heads up, there are"],
            ["{count} temporary layers (in memory), including '{name}'.",
             "{count} layers that only exist in memory, the latest being '{name}'."],
            ["They'll be lost when QGIS closes unless you make them permanent.",
             "Right-click > Make Permanent to keep the ones you need.",
             "Saving the useful ones to a GeoPackage keeps them safe."]),
        1: (["Psst.", "Just counting:", "Quick tally:"],
            ["{count} temporary layers now, '{name}' being the newest.",
             "that's {count} temporary layers, including '{name}'."],
            ["None of them survive closing QGIS.", "Make the keepers permanent.", "A GeoPackage would love to hold them."]),
        2: (["{count} temporary layers.", "We're up to {count} temporary layers.", "Another one! {count} temporary layers."],
            ["'{name}' just joined the ephemeral club.", "'{name}' included.", "'{name}' is the latest to live dangerously."],
            ["One crash and they're all gone.", "Your RAM is not a filing cabinet.", "Make Permanent exists, you know."]),
        3: (["{count} TEMPORARY LAYERS!", "WE'RE AT {count} TEMPORARY LAYERS!", "COUNT THEM: {count}!"],
            ["'{name}' TOO!", "Even '{name}'!", "'{name}' is the newest doomed layer!"],
            ["MAKE THEM PERMANENT!", "THEY WILL ALL VANISH!", "I can't watch!"]),
    },
    "temporary_layer_added": {
        1: (["'{name}' is a temporary layer.", "New temporary layer: '{name}'.", "'{name}' lives in memory only."],
            ["It disappears when QGIS closes", "It won't be saved with the project", "There's no file behind it"],
            ["unless you make it permanent.", "until you right-click > Make Permanent.", "- worth keeping in mind."]),
        2: (["'{name}': temporary.", "Ah, '{name}'. In memory.", "'{name}' has joined us. Temporarily."],
            ["Here today, gone when you close QGIS.", "It's living on borrowed RAM.", "No file, no safety net."],
            ["Make Permanent, maybe?", "Just saying.", "Your call."]),
        3: (["TEMPORARY LAYER: '{name}'!", "'{name}' IS TEMPORARY!", "ANOTHER ONE: '{name}'!"],
            ["It will VANISH!", "It's only in MEMORY!", "No file! None!"],
            ["MAKE IT PERMANENT!", "Right-click! NOW!", "I'm begging you!"]),
    },
    "generic_temporary_layer": {
        1: (["Another temporary layer called '{name}'.", "'{name}', temporary and unnamed.", "New: '{name}', in memory."],
            ["Temporary and anonymous is a risky combination.", "Future you won't know what it is, and it won't be saved.",
             "No real name and no file."],
            ["Rename it and make it permanent if it matters.", "Right-click > Rename, then Make Permanent.", ""]),
        2: (["'{name}'.", "Oh look, '{name}'.", "Welcome, '{name}'."],
            ["Temporary AND generically named.", "No name, no file, no future.", "It's like it wants to be forgotten."],
            ["Bold strategy.", "Name it. Save it. Love it.", "I give it until QGIS closes."]),
        3: (["'{name}'!", "ANOTHER '{name}'!", "'{name}' AGAIN?!"],
            ["No real name! No file!", "TEMPORARY and NAMELESS!", "It doesn't even know who it is!"],
            ["NAME IT AND SAVE IT!", "This is how data gets lost!", "Make it permanent! With a NAME!"]),
    },
    "processing_temporary_outputs": {
        1: (["That's {count} temporary outputs this session.", "Temporary output number {count}.", "{count} temporary outputs so far."],
            ["None of them are saved anywhere.", "They all disappear when QGIS closes.", "They only exist in memory."],
            ["Saving outputs to a GeoPackage keeps them safe.", "Set an output file in the algorithm dialog to keep one.", ""]),
        2: (["Temporary output #{count}.", "{count} temporary outputs.", "And that's {count} temporary outputs."],
            ["Your RAM is your filing system now.", "All of them will evaporate.", "A whole session of maybe-results."],
            ["Save one. Just one.", "A GeoPackage is right there.", "Living dangerously, I see."]),
        3: (["{count} TEMPORARY OUTPUTS!", "OUTPUT #{count}! TEMPORARY!", "{count}! TEMPORARY! OUTPUTS!"],
            ["NONE OF THEM ARE SAVED!", "THEY'LL ALL VANISH!", "IT'S ALL IN MEMORY!"],
            ["SAVE SOMETHING!", "Pick an output file! Any file!", "Why do you do this to me?"]),
    },
    "processing_repeat": {
        1: (["{algorithm} again,", "Another {algorithm},", "{algorithm} once more:"],
            ["that's {count} runs recently.", "run number {count}.", "{count} times now."],
            ["Processing > History has your previous settings.", "Batch processing can run it on many inputs at once.",
             "The Model Designer can save this as a reusable workflow."]),
        2: (["{algorithm}, attempt {count}.", "{algorithm} yet again.", "Ah, {algorithm} again."],
            ["Third time's the charm. Or the next one.", "Something not quite right yet?", "Same algorithm, new hope."],
            ["Processing > History remembers your settings.", "Batch mode exists, by the way.", "I believe in you. Mostly."]),
        3: (["{algorithm} {count} TIMES!", "{algorithm} AGAIN?!", "RUN NUMBER {count}!"],
            ["It's not going to change its mind!", "Is it right YET?", "We're in a LOOP!"],
            ["Check the History panel!", "Try batch mode!", "I'm getting dizzy!"]),
    },
}


# ------------------------------------------------- detailed settings
# Every kind of comment, grouped for the "Detailed settings" dialog.
# Ids are rule ids, plus a few non-rule comment types handled elsewhere.
COMMENT_CATEGORIES = [
    ("Saving and unsaved work", [
        ("unsaved_project", "Project not saved for a while"),
        ("uncommitted_edits", "Layer edits not saved for a while"),
        ("scratch_on_save", "Temporary layers when you save"),
        ("saved_praise", "Praise for saving"),
    ]),
    ("Temporary layers", [
        ("temporary_layer_added", "New temporary layer"),
        ("generic_temporary_layer", "New temporary layer with a generic name"),
        ("many_temporary_layers", "Lots of temporary layers"),
        ("new_scratch_layer", "New empty scratch layer"),
    ]),
    ("Layer names", [
        ("generic_layer_name", "New layer with a generic name"),
        ("lazy_names", "Several layers with default names"),
    ]),
    ("CRS and location", [
        ("crs_mismatch", "Layer CRS differs from the project"),
        ("no_crs", "Layer without a CRS"),
        ("web_mercator", "Project switched to Web Mercator"),
        ("null_island_layer", "Layer sitting at 0\u00b0, 0\u00b0"),
    ]),
    ("Processing", [
        ("processing_crs_mismatch", "Inputs in different CRSs"),
        ("buffer_in_degrees", "Distances in degrees"),
        ("processing_temporary_outputs", "Temporary outputs"),
        ("processing_repeat", "Running the same algorithm again"),
        ("processing_invalid_geometries_log", "Invalid geometries in the log"),
        ("processing_fix_geometries", "Praise for Fix Geometries"),
        ("processing_done", "Algorithm finished"),
    ]),
    ("Data checks", [
        ("invalid_geometries", "Invalid geometries in a new layer"),
        ("no_spatial_index", "Large layer without a spatial index"),
        ("empty_layer", "Empty layer"),
        ("empty_output", "Empty Processing result"),
        ("duplicate_layer", "Same data added twice"),
    ]),
    ("Errors and warnings", [
        ("error_file", "Missing files"),
        ("error_permission", "Permission problems"),
        ("error_geometry", "Geometry errors"),
        ("error_crs", "CRS and transform errors"),
        ("error_memory", "Out of memory"),
        ("error_none", "NoneType errors"),
        ("error_field", "Missing fields"),
        ("error_network", "Network errors"),
        ("error_database", "Database and SQL errors"),
        ("error_mine", "Qlippy's own errors"),
        ("processing_error", "Other Processing errors"),
        ("python_error", "Other Python errors"),
        ("error_bar", "Other errors in the message bar"),
        ("error_streak", "Lots of errors in a row"),
        ("warning_bar", "Warnings in the message bar"),
        ("success_bar", "Successes in the message bar"),
    ]),
    ("Map and performance", [
        ("slow_render", "Slow map rendering"),
        ("zoom_thrash", "Zooming in and out repeatedly"),
        ("many_layers", "Lots of layers"),
    ]),
    ("Formats and style", [
        ("shapefile", "Shapefiles"),
        ("many_shapefiles", "Projects full of shapefiles"),
        ("osm_basemap", "OpenStreetMap basemap"),
        ("first_layout", "First print layout"),
        ("comic_sans", "Comic Sans or Papyrus in a layout"),
    ]),
    ("You", [
        ("late_night", "Working late"),
        ("long_session", "Long sessions"),
        ("layer_removed", "Saying goodbye to removed layers"),
        ("layer_regret", "Removing a layer right after adding it"),
    ]),
    ("Other comments", [
        ("wander_comments", "Comments while wandering"),
        ("peek_comments", "Comments when peeking around windows"),
        ("click_remarks", "Remarks when you click Qlippy"),
    ]),
]


# ------------------------------------------------------------ personalities
# A personality wraps every comment in its own openings and endings, adds its
# own random remarks and greetings, and sometimes swaps in its favourite
# animations. The Help/Harass level still decides how harsh the content is:
# "open"/"close" are keyed by level like everything else (0 = gentle, 2 = harsh).
PERSONALITIES = {
    "classic": {
        "label": "Classic",
        "description": "The original paperclip. Helpful, cheeky or unhinged depending on the level.",
    },
    "effusive": {
        "label": "Effusive",
        "description": "Thrilled about everything you do. Even the mistakes.",
        "open": {0: ["Oh, wonderful!", "Amazing work so far!", "I love what you're doing here!",
                     "You're doing brilliantly!", "Ooh, exciting!"],
                 2: ["Okay, okay, still amazing, but:", "Oh no! But also oh YES, a learning opportunity!",
                     "Bless your heart!", "Eek! Okay!"]},
        "close": {0: ["You've got this!", "So proud of you!", "Keep shining!", "Isn't GIS wonderful?!",
                      "High five!"],
                  2: ["Still love you, though!", "Mistakes are just maps to success!", "Hugs!",
                      "You'll nail it next time! Probably!"]},
        "quips": ["Every layer you add makes the world a little more mapped!",
                  "Look at you, doing GIS! Incredible!", "That's the best CRS I've ever seen! Probably!",
                  "I just want you to know your symbology makes me happy.",
                  "You saved earlier and I still think about it.", "Is it just me or is this map AMAZING?!"],
        "greetings": ["Hello, superstar! Let's make something beautiful!", "YOU'RE HERE! Best day ever!",
                      "Welcome back, mapping legend!"],
        "anims": ["celebrate", "sparkle", "love", "dance", "bounce"],
        "wrap_chance": 0.8,
    },
    "poetic": {
        "label": "Poetic",
        "description": "Speaks in verse and sighs. Every error is a tragedy, every save an ode.",
        "open": {0: ["Hark:", "Lo,", "Consider, gentle cartographer:", "Upon this humble paper, a thought:",
                     "A whisper from the wire:"],
                 2: ["Alas!", "O woe upon this project!", "Hear now the paperclip's lament:", "Weep, ye vertices:"]},
        "close": {0: ["...and so the map unfolds.", "Thus speaks the wire.", "(A haiku was considered.)",
                      "So it goes, from pole to pole."],
                  2: ["...and the vertices weep.", "Such is the tragedy of GIS.", "Nevermore. Probably.",
                      "The graticule grows dim."]},
        "quips": ["Polygons at rest / a vertex out of its place / topology weeps.",
                  "Shall I compare thee to a GeoPackage? Thou art more lossless.",
                  "The map is not the land, but the land forgot its CRS.",
                  "Two layers diverged in a project, and I, I took the one with the spatial index.",
                  "Do not go gentle into that unsaved night.",
                  "O Mercator, Mercator, wherefore art thou so large near the poles?"],
        "greetings": ["Once more unto the map, dear friend.", "The wire awakes; the paper stirs. Let us begin.",
                      "Hail, cartographer! The world awaits its lines."],
        "anims": ["reading", "thinking", "look_around", "wave_map", "sad"],
        "wrap_chance": 0.75,
    },
    "romantic": {
        "label": "Romantic",
        "description": "Hopelessly devoted to you and your maps. A little dramatic.",
        "open": {0: ["Darling,", "My sweet cartographer,", "Mon amour,", "Oh, my dear,", "Sweetheart,"],
                 2: ["Darling, I say this with love, but:", "My heart breaks a little:", "Oh, mon dieu,",
                     "How could you, my love?"]},
        "close": {0: ["I'm only telling you because I care.", "Anything for you.", "*blushes*",
                      "Our love is like a well-indexed layer.", "xoxo"],
                  2: ["...but I'll never leave you.", "I forgive you. This time.", "How could you do this to us?",
                      "I need a moment."]},
        "quips": ["I'd follow you to any CRS.", "You had me at 'Add Vector Layer'.",
                  "Are you a spatial index? Because you make everything faster.",
                  "If you were a polygon, you'd be perfectly valid.",
                  "I'm not saying we're meant to be, but our extents overlap perfectly.",
                  "Every time you save, my wire skips a beat."],
        "greetings": ["There you are, my love. I've been waiting.", "Bonjour, mon cher cartographe.",
                      "You came back! I knew you would."],
        "anims": ["love", "giggle", "wave", "brow_wiggle"],
        "wrap_chance": 0.8,
    },
    "coach": {
        "label": "Frustrated coach",
        "description": "Believes in you. Is not happy about it. Shouts encouragement and laps.",
        "open": {0: ["Alright, team,", "Listen up,", "Okay, huddle up:", "Fundamentals, people:", "Eyes up here:"],
                 2: ["WHAT WAS THAT?!", "Are you KIDDING me?!", "I've seen better mapping in the minor leagues!",
                     "Come ON!", "Unbelievable."]},
        "close": {0: ["Now let's run it again!", "Eyes on the ball!", "That's how we win!", "Hustle!",
                      "Good. Again."],
                  2: ["Give me twenty! Vertices!", "Run it again! And this time like you MEAN it!",
                      "We practised this!", "I'm not mad. I'm disappointed. And mad.", "Laps. Now."]},
        "quips": ["Champions save their projects!", "Drop and give me twenty saves!",
                  "There's no 'I' in GIS. Wait. There is.",
                  "You don't win topology by hoping, you win it with Fix Geometries!",
                  "Pain is temporary. Temporary layers are also temporary. Save them!",
                  "I didn't come here to watch you zoom in and out all day!"],
        "greetings": ["Alright, let's go! Warm-up's over!", "Game day! Let's see some clean geometry!",
                      "You're late. Let's map."],
        "anims": ["tap_glass", "annoyed", "shake_head", "jump", "nod"],
        "wrap_chance": 0.8,
    },
    "noir": {
        "label": "Noir detective",
        "description": "A world-weary gumshoe. Every layer has a secret, and the CRS is always lying.",
        "open": {0: ["The case was simple.", "Rain on the window, data on the screen.", "I've seen this before, kid:",
                     "Another night, another project."],
                 2: ["This town is crawling with bad geometry.", "It was a dark and stormy project.",
                     "Another body in the attribute table:", "Somebody's lying, and it's the data."]},
        "close": {0: ["Case closed.", "...and the coffee was cold.", "Some layers don't want to be found.",
                      "I tipped my hat and left."],
                  2: ["Nobody's innocent in this project.", "I'd light a cigarette, but I'm a paperclip.",
                      "The CRS was lying. They always are.", "I've got a bad feeling about this layer."]},
        "quips": ["She walked in with a shapefile. I knew there'd be trouble.",
                  "In this city, every polygon has a secret.",
                  "The map said one thing. The coordinates said another.",
                  "I followed the vertices. They led me to Null Island. They always do.",
                  "Some say the attribute table doesn't lie. Some say a lot of things."],
        "greetings": ["Evening. Pull up a chair. We've got data to crack.", "Another case. Another project. Let's work.",
                      "The name's Qlippy. I hold things together."],
        "anims": ["suspicious", "search", "stare", "telescope", "look_around"],
        "wrap_chance": 0.75,
    },
}
PERSONALITY_ORDER = ["classic", "effusive", "poetic", "romantic", "coach", "noir"]
_personality = "classic"


def set_personality(personality_id):
    global _personality
    _personality = personality_id if personality_id in PERSONALITIES else "classic"


def current_personality():
    return PERSONALITIES[_personality]


def personalize(text, level, rng=random):
    """Wrap a message in the current personality's opening and/or ending."""
    personality = current_personality()
    if not text or not personality.get("open") or rng.random() > personality.get("wrap_chance", 0.0):
        return text
    opening = ending = ""
    roll = rng.random()
    if roll < 0.75:
        opening = html.escape(rng.choice(by_level(personality["open"], level)))
    if roll > 0.45:
        ending = html.escape(rng.choice(by_level(personality["close"], level)))
    return _join(opening, text, ending)


def personality_anim(anim, rng=random):
    """Sometimes swap an animation for one of the personality's favourites."""
    favourites = current_personality().get("anims")
    if favourites and anim and rng.random() < 0.3:
        return rng.choice(favourites)
    return anim


# ------------------------------------------------- failed Processing runs
RULES.update({
    "processing_source_failed": dict(_ERROR, min_level=0, anim="search", title="Processing: input problem", texts={
        0: ["Processing couldn't load an input layer ({detail}). Check the layer still exists and its source is "
            "reachable.", "An algorithm failed to read its input ({detail}). Is the file moved, locked or empty?"],
        1: ["The algorithm couldn't even open its input. Rough start.", "Input layer: unreachable. Algorithm: sulking."],
        2: ["It failed before it began: the input wouldn't load. Did it get deleted? Renamed? Abducted?",
            "Couldn't load the source layer. Can't process what isn't there, champ."],
        3: ["THE INPUT IS GONE! The algorithm opened the door and there was NOTHING THERE!",
            "SOURCE LAYER NOT FOUND! It's Null Island all over again!"],
    }),
    "processing_parameter_failed": dict(_ERROR, min_level=0, anim="thinking", title="Processing: bad parameter", texts={
        0: ["An algorithm rejected one of its parameters ({detail}). Re-open it and check the highlighted fields.",
            "One parameter wasn't accepted ({detail}). Processing > History shows exactly what was sent."],
        1: ["The algorithm didn't like one of your settings. It's picky like that.",
            "A parameter got bounced. Have a look at the dialog again."],
        2: ["Incorrect parameter value. The algorithm says no. Politely, for once.",
            "You gave it a parameter it didn't want. Like giving a cat a bath."],
        3: ["WRONG PARAMETER! It's like you're not even reading the dialog!",
            "PARAMETER REJECTED! Try numbers! Try layers! Try ANYTHING else!"],
    }),
    "processing_cancelled": dict(_ERROR, min_level=1, anim="shake_head", title=None, texts={
        1: ["Cancelled. Changed your mind? Happens to the best of us.", "Run cancelled. Was it taking too long?"],
        2: ["Cancelled! The algorithm will never know how that story ended.",
            "You cancelled it. Commitment issues, part two."],
        3: ["YOU CANCELLED IT?! It was SO close! Probably!", "CANCELLED! The suspense! The drama!"],
    }),
    "processing_warnings": {
        "min_level": 1, "cooldown": 600, "chance": 0.5, "anim": "suspicious", "title": None,
        "texts": {
            1: ["{algorithm} finished, but with warnings. The Log tab says what it skipped.",
                "{algorithm} is done, mostly. There were warnings worth a look."],
            2: ["{algorithm} 'finished'. With warnings. So, it sort of finished.",
                "Warnings in {algorithm}'s log. Probably fine. Probably."],
            3: ["{algorithm} FINISHED WITH WARNINGS! Read them! Nobody reads them!",
                "WARNINGS! In the LOG! Where nobody looks!"],
        },
    },
})

# More wordings for errors and failed runs (also at harsher levels).
_EXTRA_TEXTS = {
    "processing_error": {
        0: ["A Processing algorithm failed ({detail}). The Log tab of the algorithm dialog has the full message.",
            "That run didn't complete ({detail}). Common causes: invalid geometries, mismatched CRSs or a "
            "locked output file."],
        1: ["That algorithm fell over. Check the log; it usually says why.",
            "Processing failed. Not your fault. Probably. Check the log."],
        2: ["Processing failed. Before you blame QGIS: it's usually geometry. Or CRS. Or both.",
            "The algorithm gave up. Can't say I blame it.", "Failed. Spectacularly. The log has the autopsy."],
        3: ["PROCESSING EXPLODED. I suspect invalid geometries.", "FAILURE! The algorithm has left the building!",
            "IT DIDN'T WORK! Did you try Fix Geometries? You never try Fix Geometries!"],
    },
    "python_error": {
        2: ["A Python error. Somewhere, a plugin developer just felt a chill.",
            "Traceback! My favourite genre of literature."],
        3: ["PYTHON ERROR! It wasn't me! I was here the whole time!", "A TRACEBACK! Read it to me! I love drama!"],
    },
    "error_bar": {
        1: ["Red bar. Something went wrong. The Log Messages panel knows more.",
            "Uh-oh, an error in the message bar."],
        3: ["THE RED BAR! It's never good news! Never!", "ERROR! In RED! The worst colour!"],
    },
    "empty_output": {
        1: ["'{name}' is empty. The inputs probably don't overlap, or they're in different CRSs.",
            "Nothing came out of that one: '{name}' has no features. Do the inputs actually overlap?"],
        2: ["Congratulations, '{name}' contains exactly nothing. Masterful.",
            "'{name}': zero features. You clipped two things that never met. Romantic, really.",
            "Empty result. Your layers don't overlap. Have they even been introduced?"],
        3: ["'{name}': ZERO FEATURES! All that processing for NOTHING!",
            "EMPTY! You clipped thin air! Check the CRSs! Check the extents! Check SOMETHING!",
            "'{name}' IS A VOID! The layers never touched! It's a tragedy!"],
    },
    "processing_repeat": {},
}
for _rule_id, _texts in _EXTRA_TEXTS.items():
    for _level, _lines in _texts.items():
        RULES[_rule_id]["texts"].setdefault(_level, [])
        RULES[_rule_id]["texts"][_level].extend(_lines)

# Harsher pieces for "running the same algorithm again" (composed message).
COMPOSED["processing_repeat"][2][1].extend(["Doing the same thing again and expecting a different result?",
                                            "Same inputs, same settings, same hope."])
COMPOSED["processing_repeat"][2][2].extend(["Maybe change something this time?", "Definition of insanity, etc."])
COMPOSED["processing_repeat"][3][1].extend(["It WILL give you the SAME ANSWER!", "STOP! Change a PARAMETER!"])
COMPOSED["processing_repeat"][3][2].extend(["I can't watch this again!", "Groundhog Day, GIS edition!"])

# Detailed settings: put the new comment kinds in their category.
for _category, _comments in COMMENT_CATEGORIES:
    if _category == "Processing":
        _comments.extend([("processing_source_failed", "Failed: input couldn't be loaded"),
                          ("processing_parameter_failed", "Failed: bad parameter"),
                          ("processing_cancelled", "Cancelled runs"),
                          ("processing_warnings", "Finished with warnings")])
