/* ###
 * Export decompiled C code for all functions
 * @category Export
 */

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

public class ExportDecompiled extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0) throw new IllegalArgumentException("Use name:qualifiedName, addr:entryAddress, or all");
        for (String arg : args) {
            if (!arg.equals("all") && !arg.startsWith("name:") && !arg.startsWith("addr:"))
                throw new IllegalArgumentException("Unknown selector: " + arg);
        }
        String outputDir = System.getenv("GHIDRA_OUTPUT_DIR");
        if (outputDir == null || outputDir.isEmpty()) {
            outputDir = ".";
        }

        String programName = currentProgram.getName().replaceAll("[^a-zA-Z0-9._-]", "_");
        File outputFile = new File(outputDir, programName + "_decompiled.c");

        println("Decompiling selected functions to: " + outputFile.getAbsolutePath());

        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        decompiler.setOptions(options);

        if (!decompiler.openProgram(currentProgram)) {
            printerr("Failed to initialize decompiler: " + decompiler.getLastMessage());
            throw new IllegalStateException("Decompiler initialization failed");
        }

        try (PrintWriter writer = new PrintWriter(new FileWriter(outputFile))) {
            // Write header
            writer.println("/*");
            writer.println(" * Decompiled from: " + currentProgram.getName());
            writer.println(" * Architecture: " + currentProgram.getLanguage().getProcessor());
            writer.println(" * Compiler: " + currentProgram.getCompilerSpec().getCompilerSpecID());
            writer.println(" */");
            writer.println();

            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            int count = 0;
            int failed = 0, matched = 0, skipped = 0;
            int[] selectorMatches = new int[args.length];
            // Overall export budget, separate from auto-analysis timeout.
            long deadline = System.nanoTime() + 120L * 1000000000L;
            boolean budgetExceeded = false;

            while (functions.hasNext() && !monitor.isCancelled()) {
                Function func = functions.next();

                boolean selected = false;
                for (int i = 0; i < args.length; i++) {
                    String arg = args[i];
                    if (arg.equals("all") || arg.equals("name:" + func.getName(true)) ||
                        arg.equals("addr:" + func.getEntryPoint().toString())) {
                        selected = true;
                        selectorMatches[i]++;
                    }
                }
                if (!selected) continue;
                matched++;
                if (System.nanoTime() >= deadline) { budgetExceeded = true; skipped++; continue; }
                // Skip external/thunk functions
                if (func.isExternal() || func.isThunk()) {
                    skipped++;
                    continue;
                }

                monitor.setMessage("Decompiling: " + func.getName());

                DecompileResults results = decompiler.decompileFunction(func, (int)Math.max(1, Math.min(30, (deadline - System.nanoTime()) / 1000000000L)), monitor);

                if (results.decompileCompleted()) {
                    String decompiledCode = results.getDecompiledFunction().getC();
                    writer.println("/* Function: " + func.getName(true) + " @ " + func.getEntryPoint() + " */");
                    writer.println(decompiledCode);
                    writer.println();
                    count++;
                } else {
                    writer.println("/* FAILED TO DECOMPILE: " + func.getName(true) + " @ " + func.getEntryPoint() + " */");
                    writer.println("/* Error: " + results.getErrorMessage() + " */");
                    writer.println();
                    failed++;
                }
            }

            writer.println("/* matched=" + matched + " attempted=" + (count + failed) + " succeeded=" + count +
                " failed=" + failed + " skipped=" + skipped + " cancelled=" + monitor.isCancelled() +
                " budgetExceeded=" + budgetExceeded + " */");
            for (int i = 0; i < args.length; i++) {
                writer.println("/* selector=" + args[i].replace("*/", "* /") + " matches=" + selectorMatches[i] +
                    " ambiguous=" + (args[i].startsWith("name:") && selectorMatches[i] > 1) + " */");
            }
            if (matched == 0) writer.println("/* NO MATCHING FUNCTIONS */");
            println("Decompiled " + count + " functions (" + failed + " failed)");
        } finally {
            decompiler.dispose();
        }
    }
}
