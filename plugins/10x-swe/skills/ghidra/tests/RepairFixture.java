import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.listing.Function;
public class RepairFixture extends GhidraScript {
 public void run() throws Exception {
  var st=currentProgram.getSymbolTable();
  var a=st.createNameSpace(null,"A",SourceType.USER_DEFINED);
  var b=st.createNameSpace(null,"B",SourceType.USER_DEFINED);
  Function one=getFunctionAt(toAddr(0)); one.setName("same",SourceType.IMPORTED); one.setParentNamespace(a);
  disassemble(toAddr(16)); Function two=createFunction(toAddr(16),"same"); two.setParentNamespace(b);
  for(int i=1;i<=55;i++) { var addr=toAddr(32+i*16); disassemble(addr); Function f=createFunction(addr,"callee"+i); currentProgram.getReferenceManager().addMemoryReference(one.getEntryPoint(),f.getEntryPoint(),RefType.UNCONDITIONAL_CALL,SourceType.USER_DEFINED,0); }
  st.removeExternalEntryPoint(one.getEntryPoint());
  st.addExternalEntryPoint(two.getEntryPoint());
  var block=currentProgram.getMemory().createInitializedBlock("strings",toAddr(0x2000),2048,(byte)65,monitor,false);
  currentProgram.getMemory().setByte(toAddr(0x2000+1500),(byte)0);
  currentProgram.getListing().createData(toAddr(0x2000),new ghidra.program.model.data.StringDataType(),1501);
  runScript("ExportAll.java",new String[0]);
  runScript("ExportDecompiled.java",new String[]{"name:A::same"});
 }
}
