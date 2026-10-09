using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

class StubbsJobsLauncher {
    [STAThread]
    static void Main(string[] args) {
        if(args.Length>0) {
            if(args[0]==NativeWindowIcon.Mode||args[0]==NativeWindowIcon.SmokeMode) NativeWindowIcon.Run(args);
            return;
        }
        var root=AppDomain.CurrentDomain.BaseDirectory;
        var python=Environment.GetEnvironmentVariable("STUBBS_JOBS_PYTHON");
        if(String.IsNullOrWhiteSpace(python)) python=Path.Combine(root,@"runtime\python\pythonw.exe");
        if(!File.Exists(python)) python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), @".cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe");
        var script=Path.Combine(root,@"tools\stubbs_jobs_app.py");
        if(!File.Exists(python)||!File.Exists(script)) {
            MessageBox.Show("Faltan archivos para abrir Stubbs Jobs. Extrae todo el ZIP en una carpeta antes de abrirlo. Si sigue fallando, pide a tu IA que lea INICIO.md. Tus datos siguen guardados.","Stubbs Jobs",MessageBoxButtons.OK,MessageBoxIcon.Information);
            return;
        }
        try {
            Process.Start(new ProcessStartInfo(python,"\""+script+"\" --open") { WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden });
        } catch(Exception ex) {
            MessageBox.Show("No se pudo abrir Stubbs Jobs. "+ex.Message,"Stubbs Jobs",MessageBoxButtons.OK,MessageBoxIcon.Information);
        }
    }
}

static class NativeWindowIcon {
    internal const string Mode="StubbsJobs.WindowIcon.v1";
    internal const string SmokeMode="StubbsJobs.WindowIcon.Smoke.v1";
    const uint WM_GETICON=0x7f,WM_SETICON=0x80,WM_CLOSE=0x10;
    static readonly Guid PropertyFormat=new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
    delegate bool EnumCallback(IntPtr window,IntPtr parameter);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumCallback callback,IntPtr parameter);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr window,StringBuilder text,int length);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window,StringBuilder text,int length);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,uint process);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr process,uint flags,StringBuilder name,ref uint size);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadImage(IntPtr instance,string name,uint type,int width,int height,uint flags);
    [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
    [DllImport("user32.dll")] static extern IntPtr LoadIcon(IntPtr instance,IntPtr identifier);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr window,int command);
    [DllImport("user32.dll",SetLastError=true)] static extern IntPtr SendMessageTimeout(IntPtr window,uint message,UIntPtr first,IntPtr second,uint flags,uint timeout,out UIntPtr result);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern bool SetProp(IntPtr window,string name,IntPtr value);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetProp(IntPtr window,string name);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr RemoveProp(IntPtr window,string name);
    [DllImport("shell32.dll",PreserveSig=false)] static extern void SHGetPropertyStoreForWindow(IntPtr window,ref Guid iid,[MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref PropValue value);
    [StructLayout(LayoutKind.Sequential)] struct PropertyKey { public Guid format;public uint id;public PropertyKey(uint number){format=PropertyFormat;id=number;} }
    [StructLayout(LayoutKind.Explicit,Size=24)] struct PropValue { [FieldOffset(0)] public ushort type;[FieldOffset(8)] public IntPtr text; }
    [ComImport,Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint count);
        void GetAt(uint index,out PropertyKey key);
        void GetValue(ref PropertyKey key,out PropValue value);
        void SetValue(ref PropertyKey key,ref PropValue value);
        void Commit();
    }
    static void SetProperty(IPropertyStore store,uint id,string text) {
        var key=new PropertyKey(id);var value=new PropValue();
        if(text!=null){value.type=31;value.text=Marshal.StringToCoTaskMemUni(text);}
        try{store.SetValue(ref key,ref value);}finally{if(value.text!=IntPtr.Zero)Marshal.FreeCoTaskMem(value.text);}
    }
    static string ReadProperty(IPropertyStore store,uint id) {
        var key=new PropertyKey(id);PropValue value;store.GetValue(ref key,out value);
        try{return value.type==31?Marshal.PtrToStringUni(value.text):null;}finally{PropVariantClear(ref value);}
    }
    static IPropertyStore Properties(IntPtr window) {
        IPropertyStore store;var iid=typeof(IPropertyStore).GUID;SHGetPropertyStoreForWindow(window,ref iid,out store);return store;
    }
    static IntPtr Message(IntPtr window,uint message,uint type,IntPtr icon) {
        UIntPtr value;
        if(SendMessageTimeout(window,message,new UIntPtr(type),icon,2,250,out value)==IntPtr.Zero)throw new InvalidOperationException();
        return unchecked(new IntPtr((long)value.ToUInt64()));
    }
    static string Text(IntPtr window) {var text=new StringBuilder(512);GetWindowText(window,text,text.Capacity);return text.ToString();}
    static string WindowClass(IntPtr window) {var text=new StringBuilder(128);GetClassName(window,text,text.Capacity);return text.ToString();}
    static string ProcessPath(IntPtr window) {
        uint pid;GetWindowThreadProcessId(window,out pid);var process=OpenProcess(0x1000,false,pid);
        if(process==IntPtr.Zero)return null;
        try{var name=new StringBuilder(32768);uint size=(uint)name.Capacity;return QueryFullProcessImageName(process,0,name,ref size)?name.ToString():null;}finally{CloseHandle(process);}
    }
    static List<IntPtr> Windows() {var windows=new List<IntPtr>();EnumWindows((window,unused)=>{windows.Add(window);return true;},IntPtr.Zero);return windows;}
    static IntPtr Find(HashSet<IntPtr> before,string title,string edge) {
        var found=new List<IntPtr>();
        foreach(var window in Windows()) {
            if(before.Contains(window)||!IsWindowVisible(window)||WindowClass(window)!="Chrome_WidgetWin_1")continue;
            var caption=Text(window);
            if(caption!=title&&caption!=title+" - Microsoft Edge")continue;
            var path=ProcessPath(window);
            if(path!=null&&String.Equals(Path.GetFullPath(path),Path.GetFullPath(edge),StringComparison.OrdinalIgnoreCase))found.Add(window);
        }
        return found.Count==1?found[0]:IntPtr.Zero;
    }
    static void SmokeFindEvidence(string root,HashSet<IntPtr> before,string token,string title,string edge) {
        var items=new List<string>();
        foreach(var window in Windows()) {
            var caption=Text(window);if(!caption.Contains(token))continue;
            var path=ProcessPath(window);
            bool samePath=path!=null&&String.Equals(Path.GetFullPath(path),Path.GetFullPath(edge),StringComparison.OrdinalIgnoreCase);
            items.Add("{\"new\":"+(!before.Contains(window)).ToString().ToLowerInvariant()+",\"visible\":"+IsWindowVisible(window).ToString().ToLowerInvariant()+",\"classMatches\":"+(WindowClass(window)=="Chrome_WidgetWin_1").ToString().ToLowerInvariant()+",\"captionMatches\":"+(caption==title||caption==title+" - Microsoft Edge").ToString().ToLowerInvariant()+",\"pathMatches\":"+samePath.ToString().ToLowerInvariant()+"}");
        }
        File.WriteAllText(Path.Combine(root,"window-icon-find.json"),"["+String.Join(",",items.ToArray())+"]");
    }
    static string Quote(string argument) {
        var result=new StringBuilder("\"");int slashes=0;
        foreach(char character in argument) {
            if(character=='\\'){slashes++;continue;}
            if(character=='\"'){result.Append('\\',slashes*2+1);result.Append(character);}
            else{result.Append('\\',slashes);result.Append(character);}slashes=0;
        }
        result.Append('\\',slashes*2);return result.Append('"').ToString();
    }
    static bool Notify(Uri address,string token,string key,string status) {
        try {
            var route=status=="start"?"/api/window-icon/start":"/api/window-icon";
            var request=(HttpWebRequest)WebRequest.Create(address.GetLeftPart(UriPartial.Authority)+route);
            request.Method="POST";request.Proxy=null;request.AllowAutoRedirect=false;request.Timeout=750;request.ReadWriteTimeout=750;
            request.Headers["Origin"]=address.GetLeftPart(UriPartial.Authority);request.Headers["X-StubbsJobs"]="1";request.ContentType="application/json";
            var body=Encoding.UTF8.GetBytes("{\"token\":\""+token+"\",\"key\":\""+key+"\",\"status\":\""+status+"\"}");request.ContentLength=body.Length;
            using(var stream=request.GetRequestStream())stream.Write(body,0,body.Length);
            using(var response=(HttpWebResponse)request.GetResponse())return response.StatusCode==HttpStatusCode.OK;
        }catch{return false;}
    }
    sealed class IconSession:IDisposable {
        readonly IntPtr window,large,small,previousLarge,previousSmall;
        readonly uint pid;readonly string owner;
        readonly Dictionary<uint,string> previousProperties=new Dictionary<uint,string>();
        IPropertyStore properties;
        internal bool TaskbarVerified;
        internal IconSession(IntPtr handle,string token,string appId,string root) {
            window=handle;owner="StubbsJobs.WindowIcon."+token;GetWindowThreadProcessId(window,out pid);
            previousLarge=Message(window,WM_GETICON,1,IntPtr.Zero);previousSmall=Message(window,WM_GETICON,0,IntPtr.Zero);
            large=LoadImage(IntPtr.Zero,Path.Combine(root,@"app\assets\stubbs.ico"),1,32,32,0x10);
            small=LoadImage(IntPtr.Zero,Path.Combine(root,@"app\assets\stubbs.ico"),1,16,16,0x10);
            if(large==IntPtr.Zero||small==IntPtr.Zero){Dispose();throw new InvalidOperationException();}
            if(!SetProp(window,owner,new IntPtr(1))){Dispose();throw new InvalidOperationException();}
            try {
                properties=Properties(window);
                foreach(uint id in new uint[]{2,3,4,5})previousProperties[id]=ReadProperty(properties,id);
                SetProperty(properties,2,Quote(Path.Combine(root,"Abrir Stubbs Jobs.exe")));
                SetProperty(properties,3,Path.Combine(root,@"app\assets\stubbs.ico")+",0");
                SetProperty(properties,4,"Stubbs Jobs");
                SetProperty(properties,5,appId);
                TaskbarVerified=ReadProperty(properties,5)==appId&&ReadProperty(properties,3)==Path.Combine(root,@"app\assets\stubbs.ico")+",0"&&ReadProperty(properties,2)==Quote(Path.Combine(root,"Abrir Stubbs Jobs.exe"));
                if(!TaskbarVerified)throw new InvalidOperationException();
                if(!Ensure())throw new InvalidOperationException();
            }catch{Dispose();throw;}
        }
        internal bool Owns() {
            uint current;GetWindowThreadProcessId(window,out current);
            return IsWindow(window)&&current==pid&&GetProp(window,owner)==new IntPtr(1);
        }
        internal bool Ensure() {
            if(!Owns())return false;
            if(Message(window,WM_GETICON,1,IntPtr.Zero)!=large)Message(window,WM_SETICON,1,large);
            if(Message(window,WM_GETICON,0,IntPtr.Zero)!=small)Message(window,WM_SETICON,0,small);
            return Message(window,WM_GETICON,1,IntPtr.Zero)==large&&Message(window,WM_GETICON,0,IntPtr.Zero)==small;
        }
        internal void OverwriteForSmoke() {var stock=LoadIcon(IntPtr.Zero,new IntPtr(32512));Message(window,WM_SETICON,1,stock);Message(window,WM_SETICON,0,stock);}
        internal void CloseSmoke() {
            if(!Owns())return;
            ClearProperties();Message(window,WM_CLOSE,0,IntPtr.Zero);
            for(int i=0;i<20&&Owns();i++)Thread.Sleep(100);
        }
        void ClearProperties() {
            if(properties==null)return;
            foreach(uint id in new uint[]{2,3,4,5})try{SetProperty(properties,id,null);}catch{}
        }
        public void Dispose() {
            if(Owns()) {
                try{Message(window,WM_SETICON,1,previousLarge);Message(window,WM_SETICON,0,previousSmall);}catch{}
                if(properties!=null)foreach(var previous in previousProperties)try{SetProperty(properties,previous.Key,previous.Value);}catch{}
                RemoveProp(window,owner);
            }
            if(properties!=null){Marshal.ReleaseComObject(properties);properties=null;}
            if(large!=IntPtr.Zero)DestroyIcon(large);if(small!=IntPtr.Zero)DestroyIcon(small);
        }
    }
    internal static bool MaintainWindow(Func<bool> owns,Func<bool> ensure) {
        if(!owns())return false;
        // A busy window can time out temporarily. Keep its icons alive and retry
        // while this exact window still belongs to this opening.
        try{ensure();}catch(InvalidOperationException){}
        return owns();
    }
    internal static void Run(string[] args) {
        string root=AppDomain.CurrentDomain.BaseDirectory;Uri address=null;string token=null,key=null;
        bool smoke=args[0]==SmokeMode,opened=false;Process browser=null;
        try {
            if(args.Length!=5||!Uri.TryCreate(args[2],UriKind.Absolute,out address)||address.Scheme!="http"||address.Host!="127.0.0.1"||address.UserInfo!=""||address.AbsolutePath!="/"||!Regex.IsMatch(address.Fragment,@"^#key=[A-Za-z0-9_-]{1,120}$"))return;
            token=args[3];key=address.Fragment.Substring(5);
            if(!Regex.IsMatch(token,@"^[a-f0-9]{32}$")||!Regex.IsMatch(args[4],@"^StubbsJobs\.Desktop\.[a-f0-9]{24}$")||!address.Query.Contains("window-icon="+token)||!File.Exists(args[1])||Path.GetFileName(args[1]).ToLowerInvariant()!="msedge.exe")return;
            if(smoke&&(!File.Exists(Path.Combine(root,".synthetic-ui-fixture"))||File.ReadAllText(Path.Combine(root,".synthetic-ui-fixture"))!="synthetic-only"||!key.StartsWith("TEST-WINDOW-ICON-")))return;
            var timer=Stopwatch.StartNew();bool registered=false;
            while(timer.Elapsed.TotalSeconds<20&&!registered){registered=Notify(address,token,key,"start");if(!registered)Thread.Sleep(100);}
            var before=new HashSet<IntPtr>();bool nativeAvailable=true;
            try{before=new HashSet<IntPtr>(Windows());}catch{nativeAvailable=false;}
            var browserArguments=Quote("--app="+address.AbsoluteUri);
            if(smoke)browserArguments+=" "+Quote("--user-data-dir="+Path.Combine(root,"synthetic-edge-profile"))+" --no-first-run --disable-background-mode --disable-gpu --enable-logging "+Quote("--log-file="+Path.Combine(root,"synthetic-edge-debug.log"));
            browser=Process.Start(new ProcessStartInfo(args[1],browserArguments){UseShellExecute=false,CreateNoWindow=true});
            opened=true;
            if(!registered||!nativeAvailable){Notify(address,token,key,"window_icon_api");return;}
            var title="Stubbs Jobs · "+token;IntPtr window=IntPtr.Zero;timer.Restart();
            while(timer.Elapsed.TotalSeconds<20&&window==IntPtr.Zero){window=Find(before,title,args[1]);if(window==IntPtr.Zero)Thread.Sleep(100);}
            if(window==IntPtr.Zero){if(smoke){SmokeFindEvidence(root,before,token,title,args[1]);File.WriteAllText(Path.Combine(root,"window-icon-browser.json"),"{\"exited\":"+browser.HasExited.ToString().ToLowerInvariant()+",\"exitCode\":"+(browser.HasExited?browser.ExitCode.ToString():"null")+"}");}Notify(address,token,key,"window_not_found");return;}
            if(smoke)ShowWindow(window,0);
            using(var icons=new IconSession(window,token,args[4],root)) {
                Notify(address,token,key,"ready");
                if(smoke) {
                    icons.OverwriteForSmoke();bool repaired=icons.Ensure();bool properties=icons.TaskbarVerified;
                    icons.CloseSmoke();
                    File.WriteAllText(Path.Combine(root,"window-icon-smoke.json"),"{\"nativeIconVerified\":"+repaired.ToString().ToLowerInvariant()+",\"taskbarPropertiesVerified\":"+properties.ToString().ToLowerInvariant()+",\"closedOwnWindow\":"+(!icons.Owns()).ToString().ToLowerInvariant()+",\"restoredAfterOverwrite\":"+repaired.ToString().ToLowerInvariant()+"}");
                    return;
                }
                while(icons.Owns()) {Thread.Sleep(1500);if(!MaintainWindow(icons.Owns,icons.Ensure))break;}
            }
        }catch {
            if(address!=null&&token!=null&&key!=null)Notify(address,token,key,"window_icon_api");
            if(!opened&&address!=null)try{Process.Start(new ProcessStartInfo(address.AbsoluteUri){UseShellExecute=true});}catch{}
            // The dashboard remains available even if Windows rejects branding.
        }finally {
            // Smoke owns a separate profile and only this exact Process object.
            // Production never stops Edge or another browser process.
            if(smoke&&browser!=null)try{if(!browser.WaitForExit(4000)){browser.Kill();browser.WaitForExit(4000);}}catch{}
            if(browser!=null)browser.Dispose();
        }
    }
}
