using UnrealBuildTool;
using System.Collections.Generic;

public class BlackjackSampleEditorTarget : TargetRules
{
    public BlackjackSampleEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V4;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("BlackjackSample");
    }
}
