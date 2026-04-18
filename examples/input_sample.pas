UNIT Sample;

INTERFACE

USES
  System.SysUtils, System.Classes, Vcl.StdCtrls, Vcl.Forms;

TYPE
  TMyRecord = RECORD
    id: Integer;
    name: string;
  END;

  TMyForm = CLASS(TForm)
  PRIVATE
    data: Integer;
    caption: string;
    okButton: TButton;
    list: TStringList;
  PUBLIC
    CONSTRUCTOR Create(aOwner: TComponent); OVERRIDE;
    PROCEDURE DoSomething;
  END;

IMPLEMENTATION

CONSTRUCTOR TMyForm.Create(aOwner: TComponent);
BEGIN
  INHERITED;
  data := 0;
  caption := 'hello';
  list := TStringList.Create;
END;

PROCEDURE TMyForm.DoSomething;
VAR
  counter: Integer;
  message: string;
  mainButton: TButton;
  items: TStringList;
BEGIN
  counter:=0;
  message:='start';
  mainButton := okButton;
  items := list;
  WHILE counter < 10 DO
  BEGIN
    counter:=counter+1;
    message := message + IntToStr(counter);
  END;
  mainButton.Caption := message;
END;

FUNCTION ComputeSum(a,b:Integer):Integer;
VAR
  total:Integer;
BEGIN
  total:=a+b;
  Result:=total;
END;

END.
