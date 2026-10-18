/* Bulk export is explicit. Each artifact has one canonical producer. */
import ghidra.app.script.GhidraScript;
public class ExportAll extends GhidraScript {
    public void run() throws Exception {
        for (String script : new String[]{"ExportSummary.java", "ExportFunctions.java", "ExportStrings.java", "ExportCalls.java", "ExportSymbols.java"}) {
            runScript(script, new String[0]);
        }
        runScript("ExportDecompiled.java", new String[]{"all"});
    }
}
