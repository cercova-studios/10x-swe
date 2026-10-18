import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import java.io.*;
public class ExportSummary extends GhidraScript {
    public void run() throws Exception {
        String outputDir = System.getenv("GHIDRA_OUTPUT_DIR");
        if (outputDir == null) outputDir = ".";
        String programName = currentProgram.getName().replaceAll("[^a-zA-Z0-9._-]", "_");
        File outputFile = new File(outputDir, programName + "_summary.txt");
        println("Exporting summary to: " + outputFile.getName());

        try (PrintWriter writer = new PrintWriter(new FileWriter(outputFile))) {
            writer.println("Binary Analysis Summary");
            writer.println("=======================");
            writer.println("");
            writer.println("Cancelled: " + monitor.isCancelled());
            writer.println("File: " + currentProgram.getName());
            writer.println("Architecture: " + currentProgram.getLanguage().getProcessor());
            writer.println("Address Size: " + currentProgram.getLanguage().getLanguageDescription().getSize() + " bit");
            writer.println("Endianness: " + currentProgram.getLanguage().isBigEndian() + " (big endian)");
            writer.println("Compiler: " + currentProgram.getCompilerSpec().getCompilerSpecID());
            writer.println("");

            // Count functions
            int totalFuncs = 0, externalFuncs = 0, thunkFuncs = 0;
            FunctionIterator funcs = currentProgram.getFunctionManager().getFunctions(true);
            while (funcs.hasNext()) {
                Function f = funcs.next();
                totalFuncs++;
                if (f.isExternal()) externalFuncs++;
                if (f.isThunk()) thunkFuncs++;
            }

            writer.println("Functions:");
            writer.println("  Total: " + totalFuncs);
            writer.println("  External: " + externalFuncs);
            writer.println("  Thunks: " + thunkFuncs);
            writer.println("  User-defined: " + (totalFuncs - externalFuncs - thunkFuncs));
            writer.println("");

            // Memory sections
            writer.println("Memory Sections:");
            for (var block : currentProgram.getMemory().getBlocks()) {
                writer.println("  " + block.getName() + ": " + block.getStart() + " - " + block.getEnd() +
                    " (" + block.getSize() + " bytes)" +
                    (block.isExecute() ? " [X]" : "") +
                    (block.isWrite() ? " [W]" : "") +
                    (block.isRead() ? " [R]" : ""));
            }
        }
    }

}
