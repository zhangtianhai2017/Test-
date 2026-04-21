using UnrealBuildTool;
using System.Collections.Generic;

public class BlackjackSampleEditorTarget : TargetRules
{
    public BlackjackSampleEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("BlackjackSample");
    }
}
