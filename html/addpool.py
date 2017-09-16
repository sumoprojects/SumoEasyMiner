#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)

html = """
<!DOCTYPE html>
<html>
    <head>
        <script src="./scripts/jquery-1.9.1.min.js"></script>
        <script type="text/javascript">
            $(document).ready(function() { 
                $("input").bind("keydown", function(event) {
                    var keycode = (event.keyCode ? event.keyCode : (event.which ? event.which : event.charCode));
                    if (keycode == 13) {
                        document.getElementById('btn_ok').click();
                        return false;
                    } else if (keycode == 27) {
                        document.getElementById('btn_cancel').click();
                        return false;
                    } else  {
                        return true;
                    }
                });
            });
        
            function app_ready(){
                console.log("Add pool dialog ready!");
                app_hub.on_reset_addpool_form_event.connect(function(){
                    $("input[type=text], textarea").val("");
                    $('#pool_id').val("");
                    $('#pool_algo').val("Cryptonight");
                    $('#pool_algo').prop('disabled', false);
                    $('#pool_display_name').prop('readonly', false);
                    $('#pool_url').prop('readonly', false);
                });
                
                app_hub.on_edit_pool_event.connect(function(pool_info_json){
                    var pool_info = $.parseJSON(pool_info_json);
                    //console.log(pool_info);
                    $('#pool_algo').val(pool_info['algo']);
                    $('#pool_id').val(pool_info['id']);
                    $('#pool_display_name').val(pool_info['name']);
                    $('#pool_url').val(pool_info['url']);
                    $('#pool_username').val(pool_info['username']);
                    $('#pool_password').val(pool_info['password']);
                    
                    if(pool_info['is_fixed']){
                        $('#pool_algo').prop('disabled', true);
                        $('#pool_display_name').prop('readonly', true);
                        $('#pool_url').prop('readonly', true);
                    }
                });
            }
            
            function addEditPool(){
                var pool_id = $('#pool_id').val();
                var pool_display_name = $('#pool_display_name').val();
                var pool_url = $('#pool_url').val();
                var pool_username = $('#pool_username').val();
                var pool_password = $('#pool_password').val();
                var pool_algo = $('#pool_algo').val();
                
                app_hub.add_edit_pool(pool_id, pool_display_name, pool_url, pool_username, pool_password, pool_algo);
                
                return false;
            }
            
            function closeDialog(){
                app_hub.close_addpool_dialog();
            }
            
            function getNewAddress(){
                app_hub.get_new_address();
            }
        </script>
        <link href="./css/bootstrap.min.css" rel="stylesheet">
        <link href="./css/font-awesome.min.css" rel="stylesheet">
        <style type="text/css">
            * {
                -webkit-box-sizing: border-box;
                box-sizing: border-box;
            }
            
            body {
                -webkit-user-select: none;
                user-select: none;
                cursor: default;
                color: #76A500;
                font-family: "RoboReg", "Helvetica Neue", Helvetica, Arial, sans-serif;
                font-size: 12px;
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                overflow: hidden;
            }
            
            .add-pool .form-control{
                height: 28px;
            }
            
            .add-pool .btn{
                padding-top: 1px;
                padding-bottom: 1px;
                cursor: default;
                font-size: 12px;
                border-radius: 0;
                height: 22px;
            }
            
            .add-pool select, .add-pool input {
                font-size: 12px;
                height: 22px;
                color: #333;
            }
            
            .form-horizontal .form-group{
                padding-top: 15px;
            }
            
            .form-horizontal .form-group label{
                font-weight: bold;
            }
            
            .form-horizontal .form-group label sup{
                color: red;
            }
            
            .form-horizontal .form-group select{
                font-size: 120%;
                color: #666;
                width: 150px;
            }
            
            .form-horizontal .form-group input{
                font-size: 120%;
                width: 100%;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <form class="form-horizontal" id="add_pool_form">
                <input id="pool_id" type="hidden" value="">
                <fieldset>
                    <legend style="color: #4d94ff">Add/Edit Mining Pool</legend>
                    <div class="form-group">
                        <label for="pool_algo" class="col-xs-3 control-label">Hashing Algo <sup style="color:#333">1</sup></label>
                        <div class="col-xs-9">
                            <select id="pool_algo">
                                <option value="Cryptonight">Cryptonight</option>
                                <option value="Cryptonight-Light">Cryptonight-Light</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="pool_display_name" class="col-xs-3 control-label">Pool Name <sup>*</sup></label>
                        <div class="col-xs-9">
                            <input type="text" id="pool_display_name" placeholder="put something easy to recognize (required)" maxlength="50">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="pool_url" class="col-xs-3 control-label">URL/Port <sup>*</sup></label>
                        <div class="col-xs-9">
                            <input type="text" id="pool_url" placeholder="e.g. pool.sumokoin.com:3333 (required)" maxlength="512">
                        </div>
                    </div>
                     <div class="form-group">
                        <label for="pool_username" class="col-xs-3 control-label">Wallet Address <sup>*</sup></label>
                        <div class="col-xs-7" style="padding-right:0">
                            <input type="text" id="pool_username" placeholder="wallet address to send mined coins to (required)" maxlength="512">
                        </div>
                        <div class="col-xs-2" >
                            <button type="button" class="btn btn-primary btn-sm" onclick="getNewAddress()">Get New...</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="pool_password" class="col-xs-3 control-label">Password</label>
                        <div class="col-xs-9">
                            <input type="password" id="pool_password" placeholder="just leave this blank if not required by the pool" maxlength="512">
                        </div>
                    </div>
                    <div class="form-group">
                        <div class="col-xs-9 col-xs-offset-3">
                            <button id="btn_ok" type="button" class="btn btn-success" onclick="addEditPool(false)"><i class="fa fa-check"></i> OK</button>
                            <button id="btn_cancel" type="button" class="btn btn-warning" style="margin-left: 20px" onclick="closeDialog()"><i class="fa fa-close"></i> Cancel</button>
                            
                            <label style="color:#999; padding-top: 15px; font-weight: normal; font-size: 90%">1. Select <strong>Cryptonight</strong> hashing algorithm for SUMO (Sumokoin), XMR (Monero) and many other cryptonote-based coins; select <strong>Cryptonight-Light</strong> for AEON coin</label>
                        </div>
                    </div>
                </fieldset>
            </form>
        </div>
    </body>
</html>
"""